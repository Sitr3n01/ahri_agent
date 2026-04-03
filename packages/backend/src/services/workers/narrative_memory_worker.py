"""
Narrative Memory Worker - Synthesizes hyper-fragmented memories into a coherent narrative context.
"""
from typing import Any, Dict
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.models.database import AgentWorkerTask, UserProfile, ChatSession
from src.services.workers.base_worker import BaseWorker

import logging
logger = logging.getLogger("ahri.workers.narrative_memory")

SYNTHESIS_PROMPT = """Você é o sistema de memória consolidada da Ahri.
Sua função é analisar o Relatório de Memória Antigo e o Histórico de Conversas Recentes, extraindo fatos consolidados e os sintetizando no Perfil do Usuário em formato Markdown.

O perfil atualizado DEVE ESTAR EM TERCEIRA PESSOA e ter um tom clínico, analítico e impessoal (Ex: "O usuário é um desenvolvedor..."). Não direcione as informações para o usuário e não assuma personas. Mantenha os tópicos coesos.

Mantenha informações úteis antigas, adicione os novos fatos confirmados ou altere o status se novas decisões revogarem antigas.

Preencha as seguintes 4 seções estritamente:

# Work Context
[Descreva no que o usuário trabalha, estuda, suas responsabilidades, tech stack atual, ferramentas e metodologias.]

# Personal Context
[Descreva demografia básica, estilo de vida, preferências pessoais mapeadas de forma objetiva, nível de experiência e interesses fora do trabalho.]

# Top of Mind
[Liste de 3 a 5 tópicos recorrentes recentes que estão ocupando os últimos dias do usuário de acordo com o histórico recente. O que ele está tentando resolver agora?]

# Brief History
[Uma cronologia resumida sobre a jornada do usuário. Evolução, marcos antigos relatados e objetivos de longo prazo.]

---

DADOS DE ENTRADA:
<relatorio_antigo>
{old_report}
</relatorio_antigo>

<historico_recente>
{recent_conversations}
</historico_recente>

INSTRUÇÃO FINAL: Analise os dados acima e forneça a nova versão completa do relatório em Markdown seguindo EXATAMENTE as 4 seções descritas. Retorne APENAS o Markdown.
"""

class NarrativeMemoryWorker(BaseWorker):
    """Worker for narrative memory synthesis."""

    ENABLE_EVALUATION = False

    def __init__(self, llm_service):
        super().__init__(
            llm_service=llm_service,
            worker_type="NarrativeMemory",
            default_model="PRO" 
        )

    async def execute(
        self,
        db: AsyncSession,
        execution_id: int,
        input_data: Dict[str, Any]
    ) -> AgentWorkerTask:
        """
        Synthesize user profile.
        Input data can specify 'limit_sessions' to consider only N recent sessions.
        """
        start_time = time.time()
        task = await self._create_task_record(db, execution_id, input_data)

        try:
            limit_sessions = input_data.get("limit_sessions", 5)

            # Get User Profile
            result = await db.execute(select(UserProfile).where(UserProfile.id == 1))
            profile = result.scalar_one_or_none()

            if not profile:
                return await self._fail_task(db, task, "UserProfile not found", start_time)

            str_attributes = str(profile.attributes)
            str_preferences = str(profile.preferences)

            old_report = f"""# Work Context
{profile.work_context}
# Personal Context
{profile.personal_context}

# Legacy Attributes (Consider this for the first synthesis):
{str_attributes}
{str_preferences}

# Top of Mind
{profile.top_of_mind}
# Brief History
{profile.brief_history}
"""
            
            # Fetch recent sessions
            sessions_result = await db.execute(
                select(ChatSession).order_by(ChatSession.updated_at.desc()).limit(limit_sessions)
            )
            recent_sessions = sessions_result.scalars().all()

            # Search episodic memories for context
            from src.models.database import EpisodicMemory
            episodes_result = await db.execute(
                select(EpisodicMemory).order_by(EpisodicMemory.date.desc()).limit(10)
            )
            recent_episodes = episodes_result.scalars().all()
            
            recent_episodes_text = ""
            for ep in recent_episodes:
                recent_episodes_text += f"- [{ep.date.strftime('%Y-%m-%d')}] Topics: {ep.topics}. Summary: {ep.summary}\n"

            recent_conversations_text = ""
            for s in recent_sessions:
                from src.models.database import ChatMessage
                msg_result = await db.execute(
                    select(ChatMessage).where(ChatMessage.session_id == s.id).order_by(ChatMessage.order_index.desc()).limit(10)
                )
                msgs = reversed(msg_result.scalars().all())
                
                recent_conversations_text += f"-- Session {s.id} ({s.title}) --\n"
                if s.compacted_summary:
                    recent_conversations_text += f"Context: {s.compacted_summary}\n"
                
                for m in msgs:
                    recent_conversations_text += f"{m.role}: {m.content[:200]}\n"
                recent_conversations_text += "\n"
            
            if not recent_conversations_text.strip():
                recent_conversations_text = "Sem conversas recentes."

            prompt = SYNTHESIS_PROMPT.format(
                old_report=old_report,
                recent_conversations=f"{recent_conversations_text}\nRECENT EPISODES:\n{recent_episodes_text}"
            )

            # _call_llm returns string if no schema is provided
            response = await self._call_llm(
                prompt=prompt,
                model=getattr(self.llm.settings, "google_model_pro", self.default_model)
            )
            
            md_content = response # If string
            if isinstance(response, dict): 
                md_content = response.get("response", str(response))

            # Extract sections manually
            sections = self._parse_markdown_sections(md_content)
            
            # Update Profile
            if sections.get("Work Context"):
                profile.work_context = sections["Work Context"]
            if sections.get("Personal Context"):
                profile.personal_context = sections["Personal Context"]
            if sections.get("Top of Mind"):
                profile.top_of_mind = sections["Top of Mind"]
            if sections.get("Brief History"):
                profile.brief_history = sections["Brief History"]
                
            await db.commit()

            output = {
                "status": "success",
                "work_context": profile.work_context,
                "personal_context": profile.personal_context,
                "top_of_mind": profile.top_of_mind,
                "brief_history": profile.brief_history,
                "synthesis_raw": md_content
            }
            
            tokens = self._estimate_tokens(prompt + str(md_content))
            return await self._complete_task(db, task, output, tokens, start_time)

        except Exception as e:
            logger.error(f"NarrativeMemoryWorker failed: {e}", exc_info=True)
            return await self._fail_task(db, task, str(e), start_time)

    def _parse_markdown_sections(self, markdown: str) -> Dict[str, str]:
        import re
        sections = {
            "Work Context": "",
            "Personal Context": "",
            "Top of Mind": "",
            "Brief History": ""
        }
        
        current_section = None
        current_content = []
        
        for line in markdown.splitlines():
            # Check for headers
            header_match = re.match(r"^#+\s+(.+)$", line)
            if header_match:
                title = header_match.group(1).strip()
                # Determine which known section it matches best
                matched_key = None
                for key in sections.keys():
                    if key.lower() in title.lower():
                        matched_key = key
                        break
                        
                if matched_key:
                    if current_section and current_content:
                        sections[current_section] = "\\n".join(current_content).strip()
                    current_section = matched_key
                    current_content = []
                    continue
            
            if current_section:
                current_content.append(line)
                
        # Save last section
        if current_section and current_content:
            sections[current_section] = "\\n".join(current_content).strip()
            
        # Un-escape newlines
        for k in sections:
            sections[k] = sections[k].replace("\\n", "\n")
            
        return sections
