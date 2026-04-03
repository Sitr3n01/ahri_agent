/**
 * i18n - Internationalization store for Ahri V3.
 * Supports: pt-br (Portuguese) and en (English).
 * Persisted to localStorage.
 */
import { create } from 'zustand';

export type AppLocale = 'pt' | 'en';

const STORAGE_KEY = 'ahri_locale';

function getStoredLocale(): AppLocale {
    try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored === 'pt' || stored === 'en') return stored;
    } catch { /* noop */ }
    return 'pt'; // default
}

// ── Translation dictionaries ──────────────────────────────────
const translations = {
    // Settings header
    'settings.title': { pt: 'Configurações', en: 'Settings' },
    'settings.subtitle': { pt: 'Configure chaves de API, chat, modo agente, perfil e personas', en: 'Configure API keys, chat, agent mode, profile and personas' },

    // Tabs
    'tab.api_keys': { pt: 'Chaves API', en: 'API Keys' },
    'tab.chat': { pt: 'Chat', en: 'Chat' },
    'tab.agent': { pt: 'Agente', en: 'Agent' },
    'tab.profile': { pt: 'Perfil', en: 'Profile' },
    'tab.memory': { pt: 'Memória', en: 'Memory' },
    'tab.personas': { pt: 'Personas', en: 'Personas' },

    // API Keys tab
    'api.google_gemini': { pt: 'Google Gemini', en: 'Google Gemini' },
    'api.google_gemini_desc': { pt: 'Chaves de API para modelos Gemini Pro e tier gratuito', en: 'API keys for Gemini Pro and free tier models' },
    'api.gemini_paid': { pt: 'Chave 1', en: 'Key 1' },
    'api.gemini_free': { pt: 'Chave 2', en: 'Key 2' },
    'api.model_pro': { pt: 'Modelo Pro', en: 'Pro Model' },
    'api.model_flash': { pt: 'Modelo Flash', en: 'Flash Model' },
    'api.model_lite': { pt: 'Modelo Lite', en: 'Lite Model' },
    'api.ai_studio': { pt: 'Chave AI Studio', en: 'AI Studio API Key' },
    'api.ai_studio_hint': { pt: '6ª chave de agente (tier gratuito)', en: '6th agent key (free tier)' },
    'api.openrouter': { pt: 'OpenRouter', en: 'OpenRouter' },
    'api.openrouter_desc': { pt: 'DeepSeek R1 e outros modelos via OpenRouter', en: 'DeepSeek R1 and other models via OpenRouter' },
    'api.openrouter_key': { pt: 'Chave OpenRouter', en: 'OpenRouter API Key' },
    'api.model_name': { pt: 'Nome do Modelo', en: 'Model Name' },
    'api.google_search': { pt: 'Google Search (CSE)', en: 'Google Search (CSE)' },
    'api.google_search_desc': { pt: 'Custom Search Engine para busca na web', en: 'Custom Search Engine for web search capability' },
    'api.cse_key': { pt: 'Chave CSE', en: 'CSE API Key' },
    'api.cse_cx': { pt: 'CSE CX (ID do Motor de Busca)', en: 'CSE CX (Search Engine ID)' },
    'api.search_key_a': { pt: 'Chave Search A', en: 'Google Search Key A' },
    'api.search_key_b': { pt: 'Chave Search B', en: 'Google Search Key B' },
    'api.backup_key_hint': { pt: 'Chave de backup / rotação', en: 'Backup / rotation key' },
    'api.vision': { pt: 'Visão', en: 'Vision' },
    'api.vision_desc': { pt: 'Chaves de API para análise de imagens e multimodal', en: 'API keys for image analysis and multimodal' },
    'api.vision_key_a': { pt: 'Chave Visão A', en: 'Vision Key A' },
    'api.vision_key_b': { pt: 'Chave Visão B', en: 'Vision Key B' },
    'api.memory_manager': { pt: 'Gerenciador de Memória', en: 'Memory Manager' },
    'api.memory_manager_desc': { pt: 'Compactação e análise de perfil em background (Opcional - Recomendado Flash-lite)', en: 'Background compaction and profile analysis (Optional - Flash-lite recommended)' },
    'api.memory_manager_key': { pt: 'Chave do Gerenciador', en: 'Memory Manager Key' },
    'api.memory_manager_hint': { pt: 'Usa a chave Gemini principal se vazio. Recomendamos uma chave secundária para evitar limites de uso.', en: 'Falls back to main Gemini key if empty. Use a secondary key to avoid rate limits.' },
    'api.spotify': { pt: 'Spotify', en: 'Spotify' },
    'api.spotify_desc': { pt: 'Integração Spotify para auto-troca de persona', en: 'Spotify integration for auto-persona switching' },
    'api.client_id': { pt: 'Client ID', en: 'Client ID' },
    'api.client_secret': { pt: 'Client Secret', en: 'Client Secret' },
    'api.redirect_uri': { pt: 'URI de Redirecionamento', en: 'Redirect URI' },
    'api.other': { pt: 'Outros', en: 'Other' },
    'api.other_desc': { pt: 'DeepInfra, GitHub e chaves diversas', en: 'DeepInfra, GitHub, and miscellaneous keys' },
    'api.deepinfra_key': { pt: 'Chave DeepInfra', en: 'DeepInfra API Key' },
    'api.deepinfra_hint': { pt: 'Chave reserva DeepInfra (opcional)', en: 'Reserve DeepInfra key (optional)' },
    'api.github_token': { pt: 'Token GitHub', en: 'GitHub Token' },
    'api.github_hint': { pt: 'Para acesso mobile via Gist sync', en: 'For mobile access via Gist sync' },
    'api.gist_id': { pt: 'Gist ID', en: 'Gist ID' },
    'api.category.llm': { pt: 'Modelos (LLMs)', en: 'Models (LLMs)' },
    'api.category.agent': { pt: 'Modo Agente', en: 'Agent Mode' },
    'api.category.vision': { pt: 'Busca & Visão', en: 'Search & Vision' },
    'api.category.integrations': { pt: 'Integrações', en: 'Integrations' },
    'api.save': { pt: 'Salvar Chaves API', en: 'Save API Keys' },
    'api.save_note': { pt: 'Chaves armazenadas localmente. Para uso no servidor, adicione ao .env do backend.', en: 'Keys are stored locally. For server-side use, also add them to your backend .env file.' },

    // Chat tab
    'chat.engine': { pt: 'Motor', en: 'Engine' },
    'chat.engine_desc': { pt: 'Motor LLM padrão para conversas', en: 'Default LLM engine for chat conversations' },
    'chat.pro_label': { pt: 'Gemini Pro', en: 'Gemini Pro' },
    'chat.pro_desc': { pt: 'Melhor qualidade, requer chave paga', en: 'Best quality, paid API key required' },
    'chat.google_label': { pt: 'Flash Lite', en: 'Flash Lite' },
    'chat.google_desc': { pt: 'Tier gratuito via AI Studio', en: 'Free tier via AI Studio' },
    'chat.deepseek_label': { pt: 'DeepSeek R1', en: 'DeepSeek R1' },
    'chat.deepseek_desc': { pt: 'Via OpenRouter', en: 'Via OpenRouter' },
    'chat.local_label': { pt: 'Local (Ollama)', en: 'Local (Ollama)' },
    'chat.local_desc': { pt: 'Auto-hospedado, sem chave necessária', en: 'Self-hosted, no API key needed' },
    'chat.behavior': { pt: 'Comportamento', en: 'Behavior' },
    'chat.behavior_desc': { pt: 'Configurações de interação do chat', en: 'Chat interaction settings' },
    'chat.streaming': { pt: 'Respostas em streaming', en: 'Streaming responses' },
    'chat.streaming_desc': { pt: 'Mostrar resposta conforme é gerada', en: 'Show response as it\'s being generated' },
    'chat.auto_tags': { pt: 'Auto-salvar tags', en: 'Auto-save tags' },
    'chat.auto_tags_desc': { pt: 'Extrair e salvar tags de memória automaticamente', en: 'Automatically extract and save memory tags from conversations' },
    'chat.timestamps': { pt: 'Mostrar horários', en: 'Show timestamps' },
    'chat.timestamps_desc': { pt: 'Exibir horário em cada mensagem', en: 'Display time on each message' },
    'chat.history': { pt: 'Histórico', en: 'History' },
    'chat.reasoning': { pt: 'Raciocínio (Modelos Locais)', en: 'Reasoning (Local Models)' },
    'chat.reasoning_desc': { pt: 'Ativa deep thinking/raciocínio em modelos como Ollama R1/Qwen', en: 'Enables deep thinking tokens on models like Ollama R1/Qwen' },
    'chat.web_search': { pt: 'Pesquisa na Web (Chat)', en: 'Web Search (Chat)' },
    'chat.web_search_desc': { pt: 'Permite que o LLM pesquise na internet durante a conversa padrão', en: 'Allows the LLM to search the internet during normal chat' },
    'chat.compaction': { pt: 'Compactação', en: 'Compaction' },
    'chat.compaction_desc': { pt: 'Resumir mensagens antigas automaticamente para economizar contexto', en: 'Auto-summarize older messages to save context window' },
    'chat.compaction_threshold': { pt: 'Limite de Compactação', en: 'Compaction Threshold' },
    'chat.compaction_threshold_desc': { pt: 'Compactar quando o histórico ultrapassar esse número de mensagens', en: 'Compact when history exceeds this many messages' },
    'chat.compaction_window': { pt: 'Janela Recente', en: 'Recent Window' },
    'chat.compaction_window_desc': { pt: 'Manter as últimas N mensagens sem compactar (sempre no contexto completo)', en: 'Keep last N messages uncompacted (always in full context)' },
    'chat.compaction_model_hint': { pt: 'Usando o modelo configurado em LLM > Gerenciador de Memória', en: 'Using the model configured in LLM > Memory Manager' },
    'chat.history_desc': { pt: 'Configurações de histórico de mensagens', en: 'Message history settings' },
    'chat.max_history': { pt: 'Máximo de mensagens enviadas ao LLM', en: 'Max history messages sent to LLM' },
    'chat.max_history_hint': { pt: 'Mais mensagens = melhor contexto, mas custa mais tokens', en: 'More messages = better context, but costs more tokens' },
    'chat.save': { pt: 'Salvar Config. Chat', en: 'Save Chat Settings' },

    // Agent tab
    'agent.general': { pt: 'Geral', en: 'General' },
    'agent.general_desc': { pt: 'Configurações principais do modo agente', en: 'Core agent mode settings' },
    'agent.enabled': { pt: 'Modo agente ativo', en: 'Agent mode enabled' },
    'agent.enabled_desc': { pt: 'Permitir orquestração multi-agente', en: 'Allow multi-agent task orchestration' },
    'agent.auto_approve': { pt: 'Auto-aprovar tarefas', en: 'Auto-approve tasks' },
    'agent.auto_approve_desc': { pt: 'Pular etapa de aprovação (cuidado!)', en: 'Skip approval step for agent tasks (caution!)' },
    'agent.orchestrator': { pt: 'Orquestrador', en: 'Orchestrator' },
    'agent.orchestrator_desc': { pt: 'Modelo usado para planejamento e roteamento', en: 'Model used for task planning and routing' },
    'agent.orchestrator_model': { pt: 'Modelo do Orquestrador', en: 'Orchestrator Model' },
    'agent.workers': { pt: 'Workers', en: 'Workers' },
    'agent.workers_desc': { pt: 'Configurações de execução dos workers', en: 'Worker execution settings' },
    'agent.max_workers': { pt: 'Workers paralelos máximos', en: 'Max parallel workers' },
    'agent.max_workers_hint': { pt: 'Mais workers = mais rápido, mas usa mais quota', en: 'More workers = faster but uses more API quota' },
    'agent.tpm_limit': { pt: 'Limite TPM (tokens/minuto)', en: 'TPM Limit (tokens/minute)' },
    'agent.ollama_url': { pt: 'URL Base do Ollama', en: 'Ollama Base URL' },
    'agent.ollama_hint': { pt: 'Servidor de modelos locais para modo LOCAL', en: 'Local model server for LOCAL engine mode' },
    'agent.available_workers': { pt: 'Workers Disponíveis', en: 'Available Workers' },
    'agent.save': { pt: 'Salvar Config. Agente', en: 'Save Agent Settings' },
    'agent.available_workers_desc': { pt: 'Workers especializados que executam tarefas em paralelo', en: 'Specialized workers executing tasks in parallel' },
    'agent.api_model': { pt: 'Modelo API', en: 'API Model' },
    'agent.api_model_desc': { pt: 'Modelo para workers baseados em API', en: 'Model for API-based agent workers' },
    'agent.local_model': { pt: 'Modelo Local (Ollama)', en: 'Local Model (Ollama)' },
    'agent.local_model_desc': { pt: 'Modelo Ollama para workers locais', en: 'Ollama model for local agent workers' },
    'agent.limits': { pt: 'Limites & Workers', en: 'Rate Limits & Workers' },
    'agent.limits_desc': { pt: 'Limites de taxa e configuração de workers paralelos', en: 'Rate limiting and parallel worker configuration' },
    'agent.tpm_limit_hint': { pt: 'Tokens por min. (ex: 250k)', en: 'Tokens per min. (e.g. 250k)' },
    'agent.rpm_limit': { pt: 'Limite de RPM (por chave)', en: 'RPM Limit (per key)' },
    'agent.rpm_limit_hint': { pt: 'Reqs por min. por chave (ex: 15)', en: 'Reqs per min per key (e.g. 15)' },

    // Profile tab
    'profile.title': { pt: 'Perfil do Usuário', en: 'User Profile' },
    'profile.desc': { pt: 'Informações pessoais e preferências que as personas usam como contexto', en: 'Personal info and preferences that personas use as context' },
    'profile.identity': { pt: 'Identidade', en: 'Identity' },
    'profile.identity_desc': { pt: 'Quem você é — as personas usam isso para personalizar interações', en: 'Who you are — personas use this to personalize interactions' },
    'profile.name': { pt: 'Nome / Apelido', en: 'Name / Nickname' },
    'profile.archetype': { pt: 'Arquétipo', en: 'Archetype' },
    'profile.archetype_hint': { pt: 'Como as personas te percebem (ex: "Humanista Melancólico")', en: 'How personas perceive you (e.g. "Melancholic Humanist")' },
    'profile.learning_style': { pt: 'Estilo de Aprendizado', en: 'Learning Style' },
    'profile.learning_style_hint': { pt: 'Como você prefere aprender (ex: "Associação com Lore/Narrativa")', en: 'How you prefer to learn (e.g. "Lore/Narrative Association")' },
    'profile.interests': { pt: 'Interesses', en: 'Interests' },
    'profile.interests_desc': { pt: 'Seus interesses e hobbies — usado como contexto de conversa', en: 'Your interests and hobbies — used as conversation context' },
    'profile.interests_hint': { pt: 'Um por linha', en: 'One per line' },
    'profile.tech_stack': { pt: 'Tech Stack', en: 'Tech Stack' },
    'profile.tech_stack_desc': { pt: 'Suas tecnologias e ferramentas', en: 'Your technologies and tools' },
    'profile.tech_stack_hint': { pt: 'Separado por vírgula', en: 'Comma separated' },
    'profile.music_preferences': { pt: 'Preferências Musicais', en: 'Music Preferences' },
    'profile.music_desc': { pt: 'Gêneros e estilos — usado pelo Spotify auto-persona', en: 'Genres and styles — used by Spotify auto-persona' },
    'profile.music_hint': { pt: 'Um por linha', en: 'One per line' },
    'profile.dislikes': { pt: 'O Que Você Não Gosta', en: 'Dislikes' },
    'profile.dislikes_desc': { pt: 'Coisas que as personas devem evitar', en: 'Things personas should avoid' },
    'profile.dislikes_hint': { pt: 'Um por linha', en: 'One per line' },
    'profile.languages': { pt: 'Idiomas em Estudo', en: 'Languages Studying' },
    'profile.languages_desc': { pt: 'Idiomas com nível atual', en: 'Languages with current level' },
    'profile.save': { pt: 'Salvar Perfil', en: 'Save Profile' },

    // Personas tab
    'persona.count': { pt: 'Personas', en: 'Personas' },
    'persona.select': { pt: 'Selecione uma persona para editar', en: 'Select a persona to edit' },
    'persona.basic_info': { pt: 'Informações Básicas', en: 'Basic Info' },
    'persona.basic_info_desc': { pt: 'Nome de exibição e descrição', en: 'Display name and description' },
    'persona.display_name': { pt: 'Nome de Exibição', en: 'Display Name' },
    'persona.description': { pt: 'Descrição', en: 'Description' },
    'persona.assets': { pt: 'Assets', en: 'Assets' },
    'persona.assets_desc': { pt: 'Imagens de avatar e fundo', en: 'Avatar and background images' },
    'persona.avatar': { pt: 'Imagem do Avatar', en: 'Avatar Image' },
    'persona.background': { pt: 'Imagem de Fundo', en: 'Background Image' },
    'persona.theme_colors': { pt: 'Cores do Tema', en: 'Theme Colors' },
    'persona.theme_colors_desc': { pt: 'Cores primária e secundária', en: 'Primary and secondary accent colors' },
    'persona.primary': { pt: 'Primária', en: 'Primary' },
    'persona.secondary': { pt: 'Secundária', en: 'Secondary' },
    'persona.files': { pt: 'Arquivos da Persona', en: 'Persona Files' },
    'persona.files_desc': { pt: 'Documentos de identidade, memória e conhecimento', en: 'Identity, memory and knowledge documents' },
    'persona.persona_md': { pt: 'Identidade (persona.md)', en: 'Identity (persona.md)' },
    'persona.persona_md_desc': { pt: 'Prompt de sistema da persona — define personalidade e comportamento', en: 'Persona system prompt — defines personality and behavior' },
    'persona.memory_json': { pt: 'Memória (memory.json)', en: 'Memory (memory.json)' },
    'persona.memory_json_desc': { pt: 'Memória legada: quests, logs de sessão, buffer', en: 'Legacy memory: quests, session logs, buffer' },
    'persona.legacy_memory': { pt: 'Memória Legada (memoria_legada.md)', en: 'Legacy Memory (memoria_legada.md)' },
    'persona.legacy_memory_desc': { pt: 'Fatos de lore descobertos em conversas anteriores', en: 'Lore facts discovered in previous conversations' },
    'persona.knowledge': { pt: 'Conhecimento', en: 'Knowledge' },
    'persona.knowledge_desc': { pt: 'Arquivos de conhecimento gerados pelo sistema', en: 'System-generated knowledge files' },
    'persona.knowledge_count': { pt: 'arquivos', en: 'files' },
    'persona.open_file': { pt: 'Abrir', en: 'Open' },
    'persona.replace_file': { pt: 'Arrastar novo arquivo para substituir', en: 'Drag new file to replace' },
    'persona.open_folder': { pt: 'Abrir Pasta', en: 'Open Folder' },
    'persona.no_file': { pt: 'Arquivo não encontrado', en: 'File not found' },
    'persona.save_changes': { pt: 'Salvar Alterações', en: 'Save Changes' },
    'persona.unsaved': { pt: 'NÃO SALVO', en: 'UNSAVED' },
    'persona.unsaved_confirm': { pt: 'Você tem alterações não salvas. Descartar?', en: 'You have unsaved changes. Discard?' },

    // Worker descriptions
    'worker.rag': { pt: 'Busca vetorial ChromaDB + síntese', en: 'ChromaDB vector search + synthesis' },
    'worker.code': { pt: 'Análise, geração e execução de código', en: 'Code analysis, generation, execution' },
    'worker.shell': { pt: 'Comandos shell, operações de arquivo', en: 'Shell commands, file operations' },
    'worker.memory': { pt: 'Busca de memória em todas as camadas', en: 'Memory search across all layers' },
    'worker.web': { pt: 'Fetch de URL, scraping, sumarização', en: 'URL fetch, scraping, summarization' },
    'worker.vision': { pt: 'Análise de imagem via Gemini multimodal', en: 'Image analysis via Gemini multimodal' },
    'worker.browser': { pt: 'Automação de navegador via Playwright', en: 'Playwright browser automation' },
    'worker.router': { pt: 'Classificação e roteamento de tarefas', en: 'Task classification and routing' },

    // Common
    'common.save': { pt: 'Salvar', en: 'Save' },
    'common.cancel': { pt: 'Cancelar', en: 'Cancel' },
    'common.copy': { pt: 'Copiar', en: 'Copy' },
    'common.saved': { pt: 'Salvo', en: 'Saved' },
    'common.language': { pt: 'Idioma', en: 'Language' },
    'common.language_desc': { pt: 'Idioma da interface', en: 'Interface language' },

    // Navigation / Sidebar
    'nav.chat': { pt: 'Chat', en: 'Chat' },
    'nav.agent': { pt: 'Agente', en: 'Agent' },
    'nav.settings': { pt: 'Configurações', en: 'Settings' },
    'nav.new_chat': { pt: 'Novo Chat', en: 'New Chat' },
    'nav.sessions': { pt: 'Sessões', en: 'Sessions' },
    'nav.sync': { pt: 'Sincronizar', en: 'Sync' },
    'nav.sync_unchanged': { pt: 'Nenhuma mudança', en: 'No changes' },
    'nav.logout': { pt: 'Sair', en: 'Logout' },
    'common.rename': { pt: 'Renomear', en: 'Rename' },
    'common.delete': { pt: 'Excluir', en: 'Delete' },
    'common.theme_light': { pt: 'Modo Claro', en: 'Switch to light mode' },
    'common.theme_dark': { pt: 'Modo Escuro', en: 'Switch to dark mode' },
    'api.tester.title': { pt: 'Testador de Modelos (Gemini)', en: 'Model Tester (Gemini)' },
    'api.tester.desc': { pt: 'Verifique a disponibilidade de modelos para sua chave atual.', en: 'Check model availability for your current API key.' },
    'api.tester.check': { pt: 'Verificar Modelos', en: 'Check Models' },
    'api.tester.checking': { pt: 'Verificando...', en: 'Checking...' },
    'api.tester.no_models': { pt: 'Nenhum modelo compatível encontrado.', en: 'No compatible models found.' },
    'api.tester.copy_hint': { pt: 'Clique no ID para copiar', en: 'Click ID to copy' },
} as const;

type TranslationKey = keyof typeof translations;

// ── Store ──────────────────────────────────────────────────────
interface I18nState {
    locale: AppLocale;
    setLocale: (locale: AppLocale) => void;
    t: (key: TranslationKey) => string;
}

export const useI18nStore = create<I18nState>((set, get) => {
    const initial = getStoredLocale();

    return {
        locale: initial,

        setLocale: (locale) => {
            localStorage.setItem(STORAGE_KEY, locale);
            set({ locale });
        },

        t: (key) => {
            const locale = get().locale;
            const entry = translations[key];
            if (!entry) return key;
            return entry[locale] || entry['en'] || key;
        },
    };
});

/**
 * Hook shortcut for the t() function.
 * Usage: const t = useT();
 *        t('settings.title')
 */
export function useT() {
    const locale = useI18nStore((s) => s.locale); // React to locale changes
    const t = useI18nStore((s) => s.t);
    return t;
}
