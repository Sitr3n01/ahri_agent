"""
Vector Memory Service - Wrapper do VectorMemory (vector_brain.py).
Gerencia ChromaDB para RAG com dual-source architecture.
"""
import os
import re
import json
import glob
import logging
from datetime import datetime
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

from src.config import get_settings

logger = logging.getLogger("ahri.vector")


class VectorService:
    """Serviço de memória vetorial por persona."""

    def __init__(self, persona_name: str):
        self.persona_name = persona_name.lower().replace(" ", "_")
        settings = get_settings()

        # Diretórios da persona
        self.persona_dir = settings.personas_dir / self.persona_name
        self.rag_docs_dir = self.persona_dir / "rag_docs"
        self.knowledge_dir = self.persona_dir / "knowledge"
        self.history_dir = self.persona_dir / "history"

        for d in [self.rag_docs_dir, self.knowledge_dir, self.history_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # ChromaDB
        self.client = chromadb.PersistentClient(path=str(settings.vector_db_path))
        self.embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        self.collection = self.client.get_or_create_collection(
            name=f"memory_{self.persona_name}",
            embedding_function=self.embed_fn,
        )

    def _chunk_text(self, text: str, chunk_size: int = 1000, overlap: int = 100) -> list[str]:
        text = re.sub(r"\s+", " ", text).strip()
        chunks = []
        start = 0
        while start < len(text):
            end = start + chunk_size
            chunks.append(text[start:end])
            start += chunk_size - overlap
        return chunks

    def ingest_knowledge_base(self) -> int:
        """Processa rag_docs (estático) e knowledge (dinâmico). Retorna total de chunks."""
        tracker_file = self.persona_dir / "rag_tracker.json"
        processed_files: dict = {}

        if tracker_file.exists():
            try:
                processed_files = json.loads(tracker_file.read_text())
            except Exception as e:
                logger.warning(f"Failed to read rag_tracker.json: {e}")


        total_count = 0
        new_state = processed_files.copy()

        sources = [
            (self.rag_docs_dir, "static_lore"),
            (self.knowledge_dir, "dynamic_knowledge"),
        ]

        for dir_path, source_type in sources:
            if not dir_path.exists():
                continue

            for file_path in dir_path.glob("*.*"):
                if file_path.suffix not in (".txt", ".md"):
                    continue

                filename = file_path.name
                tracker_key = f"{source_type}/{filename}"
                current_mtime = file_path.stat().st_mtime

                if tracker_key in processed_files and processed_files[tracker_key] == current_mtime:
                    continue

                logger.info(f"[RAG] Ingesting ({source_type}): {filename}")

                try:
                    content = file_path.read_text(encoding="utf-8")

                    # Remove versão antiga
                    try:
                        self.collection.delete(where={"filename": filename, "type": source_type})
                    except Exception as e:
                        logger.warning(f"Failed to delete old version of {filename}: {e}")


                    chunks = self._chunk_text(content)
                    ids, docs, metadatas = [], [], []

                    for i, chunk in enumerate(chunks):
                        chunk_id = f"{source_type}_{filename}_{i}_{int(current_mtime)}"
                        ids.append(chunk_id)
                        docs.append(chunk)
                        metadatas.append({
                            "source": "knowledge_base",
                            "filename": filename,
                            "type": source_type,
                            "chunk_index": i,
                            "last_modified": current_mtime,
                        })
                        total_count += 1

                    if ids:
                        self.collection.add(ids=ids, documents=docs, metadatas=metadatas)
                        new_state[tracker_key] = current_mtime

                except Exception as e:
                    logger.error(f"[RAG] Error ingesting {filename}: {e}")

        try:
            tracker_file.write_text(json.dumps(new_state))
        except Exception as e:
            logger.error(f"Failed to write rag_tracker.json: {e}")


        return total_count

    def ingest_history(self) -> int:
        """Ingere histórico de chat no vetor DB."""
        if not self.history_dir.exists():
            return 0

        count = 0
        try:
            existing_ids = set(self.collection.get()["ids"])
        except Exception as e:
            logger.warning(f"Failed to get existing IDs from Chroma: {e}")
            existing_ids = set()


        for file_path in self.history_dir.glob("*.json"):
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                filename = file_path.name

                for idx, msg in enumerate(data):
                    role = msg.get("role")
                    content = msg.get("content")
                    if role not in ("user", "assistant", "model") or not content:
                        continue

                    unique_id = f"{filename}_{idx}"
                    if unique_id in existing_ids:
                        continue

                    meta = {
                        "source": filename,
                        "role": role,
                        "timestamp": msg.get("timestamp", "unknown"),
                        "type": "chat_history",
                    }
                    self.collection.add(documents=[content], metadatas=[meta], ids=[unique_id])
                    count += 1
            except Exception as e:
                logger.error(f"Error processing history file {file_path.name}: {e}")


        return count

    def add_dynamic_memory(self, title: str, content: str) -> str:
        """Escrita ativa da IA: cria arquivo em knowledge/ e re-indexa."""
        safe_title = re.sub(r"[^a-zA-Z0-9_-]", "_", title)
        filename = f"{safe_title}.md"
        file_path = self.knowledge_dir / filename

        mode = "a" if file_path.exists() else "w"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        with open(file_path, mode, encoding="utf-8") as f:
            if mode == "a":
                f.write("\n\n---\n\n")
            f.write(f"# Update: {timestamp}\n{content}")

        logger.info(f"[RAG WRITE] Memory saved: {filename}")
        self.ingest_knowledge_base()
        return filename

    def list_memories(self, source_type: str = None, limit: int = 100) -> list[dict]:
        """Lista memórias com metadata. Filtra por source_type se fornecido."""
        try:
            kwargs = {"include": ["documents", "metadatas"]}
            if source_type:
                kwargs["where"] = {"type": source_type}

            results = self.collection.get(**kwargs)

            memories = []
            if results and results["ids"]:
                for i, doc_id in enumerate(results["ids"][:limit]):
                    meta = results["metadatas"][i] if results["metadatas"] else {}
                    content = results["documents"][i] if results["documents"] else ""
                    memories.append({
                        "id": doc_id,
                        "content": content,
                        "type": meta.get("type", "unknown"),
                        "filename": meta.get("filename", ""),
                        "source": meta.get("source", ""),
                    })

            return memories
        except Exception as e:
            logger.error(f"[RAG] list_memories error: {e}")
            return []

    def get_memory(self, memory_id: str) -> dict | None:
        """Busca memória por ID."""
        try:
            result = self.collection.get(
                ids=[memory_id],
                include=["documents", "metadatas"],
            )
            if result and result["ids"]:
                meta = result["metadatas"][0] if result["metadatas"] else {}
                content = result["documents"][0] if result["documents"] else ""
                return {
                    "id": memory_id,
                    "content": content,
                    "type": meta.get("type", "unknown"),
                    "filename": meta.get("filename", ""),
                    "source": meta.get("source", ""),
                    "chunk_index": meta.get("chunk_index", 0),
                    "last_modified": meta.get("last_modified", 0),
                }
            return None
        except Exception as e:
            logger.error(f"[RAG] get_memory error: {e}")
            return None

    def update_memory(self, memory_id: str, new_content: str) -> bool:
        """Atualiza conteúdo de uma memória existente."""
        try:
            existing = self.collection.get(ids=[memory_id], include=["metadatas"])
            if not existing or not existing["ids"]:
                return False

            self.collection.update(
                ids=[memory_id],
                documents=[new_content],
            )
            return True
        except Exception as e:
            logger.error(f"[RAG] update_memory error: {e}")
            return False

    def delete_memory(self, memory_id: str) -> bool:
        """Deleta memória por ID."""
        try:
            existing = self.collection.get(ids=[memory_id])
            if not existing or not existing["ids"]:
                return False

            self.collection.delete(ids=[memory_id])
            return True
        except Exception as e:
            logger.error(f"[RAG] delete_memory error: {e}")
            return False

    def search_memory(self, query: str, n_results: int = 4, threshold: float = 1.25) -> str:
        """Busca semântica na memória. Retorna texto formatado com labels."""
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                include=["documents", "metadatas", "distances"],
            )

            memories = []
            if results["documents"]:
                for i, doc in enumerate(results["documents"][0]):
                    dist = results["distances"][0][i]
                    if dist > threshold:
                        continue

                    meta = results["metadatas"][0][i]
                    m_type = meta.get("type", "unknown")

                    if m_type == "static_lore":
                        memories.append(f"[BASE DE DADOS (FIXO)]: {doc}")
                    elif m_type == "dynamic_knowledge":
                        memories.append(f"[SUAS NOTAS (APRENDIZADO)]: {doc}")
                    else:
                        role = meta.get("role", "unknown")
                        memories.append(f"[MEMORIA DE CHAT - {role.upper()}]: {doc}")

            return "\n".join(memories)
        except Exception as e:
            logger.error(f"[RAG Search] Error: {e}")
            return ""

    # =========================================================================
    # Memory Management (Settings UI)
    # =========================================================================

    def list_files_on_disk(self) -> list[dict]:
        """Lista todos os arquivos de rag_docs/ e knowledge/ com metadados."""
        files = []
        sources = [
            (self.rag_docs_dir, "static_lore"),
            (self.knowledge_dir, "dynamic_knowledge"),
        ]
        for dir_path, source_type in sources:
            if not dir_path.exists():
                continue
            for file_path in dir_path.glob("*.*"):
                if file_path.suffix not in (".txt", ".md"):
                    continue
                stat = file_path.stat()
                chunk_count = self.get_chunk_count_for_file(file_path.name, source_type)
                files.append({
                    "filename": file_path.name,
                    "source_type": source_type,
                    "size_bytes": stat.st_size,
                    "chunk_count": chunk_count,
                    "last_modified": stat.st_mtime,
                })
        return files

    def get_file_absolute_path(self, filename: str, source_type: str) -> Path | None:
        """Retorna o caminho absoluto do arquivo no disco."""
        if source_type == "static_lore":
            file_path = self.rag_docs_dir / filename
        else:
            file_path = self.knowledge_dir / filename

        if file_path.exists():
            return file_path.resolve()
        return None

    def get_chunk_count_for_file(self, filename: str, source_type: str) -> int:
        """Retorna quantos chunks existem no ChromaDB para um arquivo."""
        try:
            results = self.collection.get(
                where={"$and": [{"filename": filename}, {"type": source_type}]},
            )
            return len(results["ids"]) if results and results["ids"] else 0
        except Exception:
            # Fallback: try without $and (older ChromaDB versions)
            try:
                results = self.collection.get(where={"filename": filename})
                return len(results["ids"]) if results and results["ids"] else 0
            except Exception as e:
                logger.warning(f"[RAG] get_chunk_count_for_file error: {e}")
                return 0

    def delete_file_and_chunks(self, filename: str, source_type: str) -> int:
        """Deleta arquivo do disco + TODOS os chunks do ChromaDB + entrada no tracker.
        Corrige o bug da V2 onde esquecer não removia o arquivo do disco."""
        deleted_chunks = 0

        # 1. Delete ChromaDB chunks
        try:
            results = self.collection.get(where={"filename": filename})
            if results and results["ids"]:
                self.collection.delete(ids=results["ids"])
                deleted_chunks = len(results["ids"])
                logger.info(f"[RAG] Deleted {deleted_chunks} chunks for {filename}")
        except Exception as e:
            logger.error(f"[RAG] Error deleting chunks for {filename}: {e}")

        # 2. Delete physical file from disk
        if source_type == "static_lore":
            file_path = self.rag_docs_dir / filename
        else:
            file_path = self.knowledge_dir / filename

        if file_path.exists():
            try:
                file_path.unlink()
                logger.info(f"[RAG] Deleted file: {file_path}")
            except Exception as e:
                logger.error(f"[RAG] Error deleting file {file_path}: {e}")

        # 3. Remove tracker entry
        tracker_file = self.persona_dir / "rag_tracker.json"
        if tracker_file.exists():
            try:
                tracker = json.loads(tracker_file.read_text())
                tracker_key = f"{source_type}/{filename}"
                if tracker_key in tracker:
                    del tracker[tracker_key]
                    tracker_file.write_text(json.dumps(tracker))
                    logger.info(f"[RAG] Removed tracker entry: {tracker_key}")
            except Exception as e:
                logger.error(f"[RAG] Error updating tracker: {e}")

        return deleted_chunks

    def get_collection_stats(self) -> dict:
        """Retorna estatísticas da coleção ChromaDB."""
        stats = {"total": 0, "by_type": {}}
        try:
            all_data = self.collection.get(include=["metadatas"])
            if all_data and all_data["ids"]:
                stats["total"] = len(all_data["ids"])
                for meta in (all_data["metadatas"] or []):
                    m_type = meta.get("type", "unknown") if meta else "unknown"
                    stats["by_type"][m_type] = stats["by_type"].get(m_type, 0) + 1
        except Exception as e:
            logger.error(f"[RAG] get_collection_stats error: {e}")
        return stats

    def force_reindex(self) -> int:
        """Limpa tracker e re-ingere toda a base de conhecimento."""
        tracker_file = self.persona_dir / "rag_tracker.json"
        if tracker_file.exists():
            try:
                tracker_file.write_text("{}")
            except Exception as e:
                logger.error(f"[RAG] Error clearing tracker: {e}")

        return self.ingest_knowledge_base()

    def search_with_metadata(self, query: str, source_type: str | None = None, limit: int = 20) -> list[dict]:
        """Busca semântica retornando resultados estruturados com metadata."""
        try:
            kwargs: dict = {
                "query_texts": [query],
                "n_results": min(limit, 50),
                "include": ["documents", "metadatas", "distances"],
            }
            if source_type:
                kwargs["where"] = {"type": source_type}

            results = self.collection.query(**kwargs)

            memories = []
            if results["documents"]:
                for i, doc in enumerate(results["documents"][0]):
                    meta = results["metadatas"][0][i] if results["metadatas"] else {}
                    dist = results["distances"][0][i] if results["distances"] else 0
                    memories.append({
                        "id": results["ids"][0][i] if results["ids"] else "",
                        "content": doc,
                        "type": meta.get("type", "unknown"),
                        "filename": meta.get("filename", ""),
                        "source": meta.get("source", ""),
                        "distance": dist,
                    })
            return memories
        except Exception as e:
            logger.error(f"[RAG] search_with_metadata error: {e}")
            return []


# Cache de instâncias por persona
_vector_instances: dict[str, VectorService] = {}


def get_vector_service(persona_name: str) -> VectorService:
    """Retorna (ou cria) uma instância de VectorService para a persona."""
    key = persona_name.lower().replace(" ", "_")
    if key not in _vector_instances:
        _vector_instances[key] = VectorService(key)
    return _vector_instances[key]
