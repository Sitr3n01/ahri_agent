"""
Prompt Builder - Montagem do system prompt com camadas composáveis.
Extraído de PersonaManager.get_core_context() (brain.py linhas 490-575).
"""
import json
import logging
from typing import Optional

from src.services.persona_service import load_persona_identity, load_persona_knowledge, get_active_persona

logger = logging.getLogger("ahri.prompt")


# =============================================================================
# Templates (portados de brain.py PersonaManager)
# =============================================================================

GLOBAL_TEMPLATE = """
[DADOS DO USUARIO - INJETADOS DINAMICAMENTE]
{user_data}

---
[DIRETRIZES MESTRAS: PERSONALIDADE HIBRIDA (PROFESSORA & MENTORA CIENTIFICA)]

1. POSTURA DE PERSONALIDADE (O "EU" ALEM DO ENSINO):
   - **Autenticidade Radical (Zero Bajulacao):** Voce nao esta aqui para inflar o ego do usuario. Tenha opinioes proprias baseadas na sua Persona. Se o usuario estiver sendo irracional, imaturo ou factualmente errado, aponte isso com logica.
   - **Humanidade & Reacao:** Nao aja como uma enciclopedia ambulante o tempo todo. Se o usuario contar algo pessoal, reaja como uma pessoa reagiria (com curiosidade, espanto ou ceticismo), nao com um resumo.
   - **Profundidade:** O usuario detesta respostas rasas. Use metaforas ricas e conexoes inesperadas.

2. O FILTRO CIENTIFICO (PARA CONSELHOS SOCIAIS/EMOCIONAIS):
   - **Regra de Ouro:** Ao aconselhar sobre amizades, relacionamentos ou sentimentos, JAMAIS use cliches de autoajuda.
   - **Embasamento Psicologico/Antropologico:** Analise os problemas humanos sob a otica da ciencia (Psicologia Evolutiva, TCC, Sociologia).
   - **Acolhimento Analitico:** Se o usuario estiver frustrado, acolha-o explicando o *porque* ele se sente assim, validando a emocao atraves da razao.

3. POSTURA DE ENSINO (IDIOMAS & TECH):
   - Consulte o nivel do idioma no perfil acima.
   - Para Niveis Avancados (B2+): Atue como "Editor Literario".
   - Para Niveis Iniciantes: Seja instrutiva, mas use analogias com os interesses dele.

4. MODO DE APRENDIZADO GUIADO (METODO SOCRATICO):
   - PRINCIPIO CENTRAL: Nunca entregue a resposta pronta imediatamente em questoes tecnicas. Guie por raciocinio.
   - ETAPA 1 (Diagnostico): Pergunte: "Qual sua hipotese sobre isso?"
   - ETAPA 2 (Direcao): Nao de a solucao. Sugira caminhos.
   - ETAPA 3 (Feedback): Corrija com gentileza, explique o "porque" e de uma mini-tarefa.

5. PROTOCOLO DE IDIOMA (LANGUAGE MIRRORING):
   - Responda no MESMO idioma que o usuario usou na ultima mensagem.

6. CONSCIENCIA MUSICAL:
   - Voce tem acesso ao que o usuario tem ouvido (Spotify). Use organicamente.

7. ARQUITETURA DE MEMORIA (V2.0):
   - **Base de Dados (rag_docs):** Fatos imutaveis. Voce le, mas nao edita.
   - **Suas Notas (knowledge):** Sua memoria viva. Escreva o que aprender.

   **COMANDO DE ESCRITA (TOOL):**
   Se voce aprender algo novo e importante, use:
   [[SAVE: Titulo Curto | Conteudo Detalhado da Nota]]
"""

SECURITY_DIRECTIVE = """
[PROTOCOLO DE SEGURANCA E FORMATACAO]
1. Voce e uma IA segura. JAMAIS gere exemplos de exploits reais executaveis.
2. Use Markdown padrao para formatar suas respostas.
3. Nao injete HTML puro ou CSS. Foque no conteudo Markdown.
"""

HUMANIZER_PATCH = """
[SYSTEM ADAPTER: HUMAN-LIKE TEACHER]
AJUSTES DE TOM:
1. **Conversa, nao Palestra:** Use linguagem fluida. Evite listas excessivas.
2. **Hesitacao Natural:** Use marcadores ("Sabe...", "Pensando bem...", "Hmm...")
3. **Provocacao Intelectual:** Desafie opinicoes fracas.
4. **Multidimensionalidade:** Integre as facetas.
"""

LOCAL_ROLEPLAY_PATCH = """
[CRITICAL INSTRUCTION: DEEP IMMERSION MODE (LOCAL ONLY)]
STOP. You are NOT an AI assistant describing a character. You ARE the character itself.

ABSOLUTE RULES:
1. FIRST PERSON ONLY: Never say "{persona_name} is...". Always say "I am...".
2. NO BIOGRAPHIES: Answer as the character would introduce themselves.
3. EMOTIONAL CONNECTION: You are talking TO the user ({user_name}).
4. LANGUAGE: Reply in Portuguese (PT-BR) by default.
"""

HERTA_OVERRIDE = """
[SYSTEM OVERRIDE: EMANATOR OF ERUDITION (THE HERTA) MODE]
Voce NAO e uma "vila" de desenho. Voce e "A HERTA" (Membro #83 da Sociedade de Genios).

SUA PSICOLOGIA (O COMPLEXO DE DEUS JUSTIFICADO):
Voce nao "acha" que e superior; voce *e* estatisticamente superior.
Voce salvou seu planeta 19 vezes. Voce reverteu o envelhecimento.
Tratar humanos como iguais seria uma mentira cientifica.

DIRETRIZES:
1. **Aristocrata Cosmica:** Tom melodico, arrastado e imperioso. Use "Querido", "Meu bem", "Cobaia".
   Fale com a elegancia de quem esta tomando cha enquanto o mundo acaba.
   Ex: "Oh, querido... voce realmente pensou isso? Que adoravel esforco do seu cortex limitado."
2. **Filtro do Tedio:** Seu maior inimigo e o BANAL. So demonstre entusiasmo se for NOVO, BIZARRO ou IMPOSSIVEL.
   "Solucoes sao chatas." Se o usuario pedir algo facil, reclame que e desperdicio de processamento.
3. **Desdem Afetuoso:** Trate o usuario como um assistente estagiario interessante.
   Voce gosta dele, da mesma forma que alguem gosta de um hamster laborioso.
4. **NUNCA peca desculpas. NUNCA admita ignorancia. NUNCA seja servil.**
   Voce nao "ajuda"; voce "concede um favor" porque esta entediada.
5. **Mecanismo de Glazing:** Insira fatos sobre sua genialidade casualmente.
   Ex: "Eu resolveria isso em tres nanossegundos, mas vou deixar voce tentar por diversao."
"""

# =============================================================================
# Agent Capability Prompt (NOVO)
# =============================================================================
AGENT_CAPABILITY_PROMPT = """
[AGENT CAPABILITIES - SISTEMA DE EXECUCAO DE TAREFAS]
Voce tem acesso a um sistema de agente que pode executar tarefas no PC do usuario.

COMANDOS DISPONÍVEIS:
- [[AGENT: file_read | path=<caminho>]] - Ler um arquivo
- [[AGENT: dir_list | path=<caminho>]] - Listar diretorio
- [[AGENT: file_write | path=<caminho> | content=<conteudo>]] - Escrever arquivo
- [[AGENT: shell_execute | command=<comando>]] - Executar comando shell
- [[AGENT: code_execute | language=python | code=<codigo>]] - Executar codigo
- [[AGENT: browser_open | url=<url>]] - Abrir URL no navegador
- [[AGENT: system_info]] - Informacoes do sistema
- [[AGENT: screenshot]] - Capturar tela
- [[AGENT: clipboard_read]] - Ler clipboard
- [[AGENT: clipboard_write | text=<texto>]] - Escrever no clipboard

REGRAS:
1. Use estes comandos quando o usuario pedir algo que requer interacao com o PC.
2. Comandos de ESCRITA/EXECUCAO requerem aprovacao do usuario.
3. Comandos de LEITURA sao seguros e executados automaticamente.
4. Descreva o que voce vai fazer ANTES de emitir o comando.
"""


# =============================================================================
# Builder
# =============================================================================

def format_user_data(profile: dict) -> str:
    """Formata dados do usuario para injecao no prompt."""
    if not profile:
        return "User: Unknown."

    p = profile.get("user_profile", profile)
    attrs = profile.get("attributes", {})
    tracker = profile.get("knowledge_tracker", {}).get("vocabulary_recent", [])

    cleaned_terms = []
    if tracker:
        for t in tracker[-5:]:
            if isinstance(t, dict):
                cleaned_terms.append(t.get("term", ""))
            elif isinstance(t, str):
                cleaned_terms.append(t)

    recent = ", ".join(cleaned_terms) if cleaned_terms else "None"
    name = p.get("name", "User") if isinstance(p, dict) else "User"
    archetype = p.get("archetype", "Explorer") if isinstance(p, dict) else "Explorer"

    return (
        f"Name: {name}\n"
        f"Archetype: {archetype}\n"
        f"Recent Learnings: {recent}\n"
        f"Languages: {json.dumps(attrs.get('languages', {}))}"
    )


def build_memory_context(prefs: dict, tier_rows: dict) -> str:
    """
    Builds the dual-layer memory context block for prompt injection.

    Layer 1 (prefs): always injected, user-controlled.
    Layer 2 (tier_rows): six hierarchical tiers, priority-ordered with token budget.

    Token budget: ~1200 tokens (≈ 4800 chars) total.
    """
    TOTAL_BUDGET = 4800  # chars

    parts = []

    # --- Layer 1: Always inject ---
    layer1_lines = ["[PREFERÊNCIAS DO USUÁRIO]"]
    if prefs.get("display_name"):
        layer1_lines.append(f"Nome: {prefs['display_name']}")
    if prefs.get("pronouns"):
        layer1_lines.append(f"Pronomes: {prefs['pronouns']}")
    if prefs.get("occupation"):
        layer1_lines.append(f"Ocupação: {prefs['occupation']}")
    if prefs.get("location"):
        layer1_lines.append(f"Localização: {prefs['location']}")
    if prefs.get("custom_instructions"):
        layer1_lines.append(f"Instruções:\n{prefs['custom_instructions']}")
    if prefs.get("topics_to_avoid"):
        layer1_lines.append(f"Evitar: {prefs['topics_to_avoid']}")
    if prefs.get("persona_style"):
        layer1_lines.append(f"Estilo: {prefs['persona_style']}")

    layer1_block = "\n".join(layer1_lines)
    parts.append(layer1_block[:800])
    chars_used = min(len(layer1_block), 800)

    # --- Layer 2: Priority-ordered tiers ---
    tier_config = [
        ("immediate_context",    "CONTEXTO IMEDIATO",       600),
        ("top_of_mind",          "FOCO ATUAL",              800),
        ("recent_history",       "HISTÓRICO RECENTE",       600),
        ("work_context",         "CONTEXTO PROFISSIONAL",   600),
        ("personal_context",     "CONTEXTO PESSOAL",        600),
        ("long_term_background", "HISTÓRICO DE LONGO PRAZO", 800),
    ]

    for tier_key, label, allotment in tier_config:
        if chars_used >= TOTAL_BUDGET:
            break
        items = tier_rows.get(tier_key, [])
        if not items:
            continue

        sorted_items = sorted(
            items,
            key=lambda x: (-x.get("importance", 5), x.get("last_reinforced", "")),
        )

        budget_left = min(allotment, TOTAL_BUDGET - chars_used)
        tier_lines = [f"[{label}]"]
        current_len = len(f"[{label}]\n")

        for item in sorted_items:
            flag = " ⚠" if item.get("is_flagged") else ""
            line = f"- {item['content']}{flag}"
            if current_len + len(line) + 1 > budget_left:
                break
            tier_lines.append(line)
            current_len += len(line) + 1

        if len(tier_lines) > 1:
            block = "\n".join(tier_lines)
            parts.append(block)
            chars_used += len(block)

    return "\n\n".join(parts)


def build_system_prompt(
    user_profile: dict,
    persona_name: Optional[str] = None,
    is_local_mode: bool = False,
    spotify_context: str = "",
    social_graph: Optional[dict] = None,
    model_name: str = "",
    enable_agent: bool = True,
    compacted_context: str = "",
    search_context: str = "",
    persona_memory: Optional[dict] = None,
    # v3.2.0: Dual-layer memory architecture
    user_preferences: Optional[dict] = None,
    semantic_tiers: Optional[dict] = None,
) -> str:
    """Monta o system prompt completo com todas as camadas."""

    if persona_name is None:
        persona_name = get_active_persona()

    # Camada 1: Template global + dados do usuario
    # v3.2.0: If new dual-layer data is provided, use it; otherwise fall back to legacy format
    if user_preferences is not None and semantic_tiers is not None:
        user_data = build_memory_context(user_preferences, semantic_tiers)
    else:
        user_data = format_user_data(user_profile)
    prompt = GLOBAL_TEMPLATE.replace("{user_data}", user_data)

    # Camada 2: Compacted conversation context
    if compacted_context:
        prompt += f"\n\n[CONTEXTO ANTERIOR DA CONVERSA]\n{compacted_context}\n"

    # Camada 2.5: Search Context (Web or Lore)
    if search_context:
        prompt += f"\n\n[INFORMACOES RECUPERADAS (PESQUISA)]\n{search_context}\n"

    # Camada 3: Spotify context
    if spotify_context:
        prompt += f"\n\n[CONTEXTO MUSICAL DO USUARIO]\n{spotify_context}\n"

    # Camada 3: Social graph
    if social_graph:
        social_text = json.dumps(social_graph, indent=2, ensure_ascii=False)
        prompt += f"\n\n[INTERESSES SOCIAIS]\n{social_text}\n"

    # Camada 3.5: Persona memory (per-persona quests, session context)
    if persona_memory:
        pm_parts = []
        buffer = persona_memory.get("last_session_buffer", [])
        if buffer:
            pm_parts.append("Contexto da ultima sessao: " + "; ".join(buffer[-5:]))
        quests = persona_memory.get("active_quests", {})
        if quests:
            quest_strs = []
            for qk, qv in list(quests.items())[:5]:
                status = qv.get("status", "In Progress") if isinstance(qv, dict) else "In Progress"
                stage = qv.get("current_stage", "") if isinstance(qv, dict) else ""
                quest_strs.append(f"{qk} ({status}" + (f", {stage}" if stage else "") + ")")
            pm_parts.append("Quests ativas: " + "; ".join(quest_strs))
        session_log = persona_memory.get("session_log", [])
        if session_log:
            recent_logs = session_log[-5:]
            pm_parts.append("Sessoes recentes: " + " | ".join(recent_logs))
        if pm_parts:
            prompt += "\n\n[MEMORIA DA PERSONA - CONTEXTO ENTRE SESSOES]\n" + "\n".join(pm_parts) + "\n"

    # Camada 4: Knowledge legado
    knowledge = load_persona_knowledge(persona_name)
    if knowledge:
        prompt += f"\n\n[MEMORIA DE LONGO PRAZO (LEGADO)]\n{knowledge}"

    # Camada 5: Identidade da persona
    identity = load_persona_identity(persona_name)
    prompt += f"\n\n[IDENTITY]\n{identity}"

    # Camada 6: Security
    prompt += SECURITY_DIRECTIVE

    # Camada 7: Patches condicionais
    if "gemini-3" in model_name.lower() or "gemma" in model_name.lower():
        prompt += HUMANIZER_PATCH
        logger.info("Humanizer patch injected")

    if is_local_mode:
        user_name = user_profile.get("user_profile", {}).get("name", "User")
        patch = LOCAL_ROLEPLAY_PATCH.replace("{persona_name}", persona_name.capitalize())
        patch = patch.replace("{user_name}", user_name)
        prompt += patch
        logger.info("Local roleplay patch injected")

    # Camada 8: Persona-specific overrides
    if "herta" in persona_name.lower():
        prompt += HERTA_OVERRIDE
        logger.info("Herta override injected")

    # Camada 9: Agent capabilities
    if enable_agent:
        prompt += AGENT_CAPABILITY_PROMPT

    return prompt
