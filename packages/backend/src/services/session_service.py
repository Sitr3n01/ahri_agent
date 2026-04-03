"""
Session Service - CRUD de sessoes de chat.
Portar de MemoryHandler (brain.py linhas 284-351).
"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import ChatSession, ChatMessage
from src.services.persona_service import get_active_persona

logger = logging.getLogger("ahri.session")


class SessionService:
    """Servico de sessoes de chat - usa SQLite no lugar de JSON files."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_sessions(self, persona_name: Optional[str] = None) -> list[dict]:
        """Lista sessoes da persona ativa, ordenadas por data."""
        if persona_name is None:
            persona_name = get_active_persona()

        # Query com contagem de mensagens
        stmt = (
            select(
                ChatSession,
                func.count(ChatMessage.id).label("message_count"),
            )
            .outerjoin(ChatMessage, ChatSession.id == ChatMessage.session_id)
            .where(ChatSession.persona_name == persona_name.lower())
            .group_by(ChatSession.id, ChatSession.updated_at)
            .order_by(ChatSession.updated_at.desc())
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        return [
            {
                "id": session.id,
                "title": session.title or f"Chat {session.created_at.strftime('%Y-%m-%d %H:%M')}",
                "persona_name": session.persona_name,
                "message_count": count,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
            }
            for session, count in rows
        ]

    async def create_session(self, title: str = "", persona_name: Optional[str] = None) -> dict:
        """Cria uma nova sessao de chat."""
        if persona_name is None:
            persona_name = get_active_persona()

        session = ChatSession(
            persona_name=persona_name.lower(),
            title=title or f"Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)

        return {
            "id": session.id,
            "title": session.title,
            "persona_name": session.persona_name,
            "message_count": 0,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
        }

    async def get_session(self, session_id: int) -> Optional[dict]:
        """Carrega uma sessao com todas as mensagens."""
        result = await self.db.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if session is None:
            return None

        msg_result = await self.db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.order_index)
        )
        messages = msg_result.scalars().all()

        return {
            "id": session.id,
            "title": session.title,
            "persona_name": session.persona_name,
            "message_count": len(messages),
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "images": msg.images or [],
                    "timestamp": msg.timestamp,
                    "meta": msg.meta or {},
                }
                for msg in messages
            ],
        }

    async def add_message(
        self,
        session_id: int,
        role: str,
        content: str,
        images: Optional[list] = None,
        timestamp: str = "",
        meta: Optional[dict] = None,
    ) -> int:
        """Adiciona uma mensagem a sessao."""
        # Calcula order_index
        result = await self.db.execute(
            select(func.max(ChatMessage.order_index))
            .where(ChatMessage.session_id == session_id)
        )
        max_idx = result.scalar() or 0

        if not timestamp:
            timestamp = datetime.now().strftime("%H:%M:%S")

        msg = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            images=images or [],
            timestamp=timestamp,
            order_index=max_idx + 1,
            meta=meta or {},
        )
        self.db.add(msg)

        # Atualiza updated_at da sessao
        sess_result = await self.db.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        )
        session = sess_result.scalar_one_or_none()
        if session:
            session.updated_at = datetime.utcnow()

        await self.db.commit()
        await self.db.refresh(msg)
        return msg.id

    async def rename_session(self, session_id: int, title: str) -> bool:
        """Renomeia uma sessao."""
        if not title or len(title) > 200:
            raise ValueError("Invalid title")
        
        result = await self.db.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if session is None:
            return False

        session.title = title
        await self.db.commit()
        return True

    async def get_session_summary(self, session_id: int) -> str:
        """Retorna o compacted_summary de uma sessão."""
        result = await self.db.execute(
            select(ChatSession.compacted_summary).where(ChatSession.id == session_id)
        )
        return result.scalar() or ""

    async def update_session_summary(self, session_id: int, summary: str, compacted_up_to: int) -> None:
        """Atualiza o summary de compactação da sessão."""
        result = await self.db.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if session:
            session.compacted_summary = summary
            session.compacted_up_to = compacted_up_to
            await self.db.commit()

    async def delete_session(self, session_id: int) -> bool:
        """Deleta uma sessao e suas mensagens."""
        result = await self.db.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        )
        session = result.scalar_one_or_none()
        if session is None:
            return False

        # Deleta mensagens primeiro, depois a sessão
        await self.db.execute(
            delete(ChatMessage).where(ChatMessage.session_id == session_id)
        )
        await self.db.execute(
            delete(ChatSession).where(ChatSession.id == session_id)
        )
        await self.db.commit()
        return True
