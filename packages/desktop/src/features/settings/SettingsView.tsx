import React, { useState, useEffect, useRef } from 'react';
import { useChatStore } from '@/stores/chat-store';
import { usePersonaStore } from '@/stores/persona-store';
import { useAuthStore } from '@/stores/auth-store';
import { useThemeStore } from '@/stores/theme-store';
import { useI18nStore, useT } from '@/stores/i18n-store';
import { api } from '@/api/client';
import { getPersonaTheme, mergePersonaTheme } from '@ahri/shared';
import { usePersonaTheme } from '@/hooks/usePersonaTheme';
import { 
  Activity, Beaker, BookOpen, Brain, CheckCircle, ChevronLeft, ChevronRight, Cloud, Code, Cpu,
  Database, Eye, FileText, FlaskConical, Globe, Image as ImageIcon, Key, Layout, Network,
  Palette, Plus, Save, Search, Settings, Shield, Smartphone, Sparkles, Terminal, Trash2,
  User, X, Zap
} from 'lucide-react';
import { ColorPicker } from '@/components/ColorPicker';
import { ImageUpload } from './ImageUpload';
import { PersonaFilesPanel } from './PersonaFilesPanel';
import { ProfileFilesPanel } from './ProfileFilesPanel';
import { TagInput } from './TagInput';
import { MemoryTab } from './MemoryTab';
import { InstrucoesTab } from './InstrucoesTab';

// ── Persona Image Positioning ─────────────────────────────────
const PERSONA_IMAGE_POSITIONS: Record<string, string> = {
  ahri: '50% 35%',
  kafka: '50% 35%',
  robin: '50% 35%',
  furina: '50% 35%',
  sparkle: '50% 35%',
  frieren: '50% 35%',
  herta: '50% 35%',
  shorekeeper: '50% 35%',
  cantarella: '50% 35%',
  maomao: '50% 35%',
  'yae miko': '50% 35%',
  rakan: '50% 35%',
  'march 7th': '50% 35%',
  cartethyia: '50% 35%',
  cyrene: '50% 35%',
  'carlotta montelli': '50% 35%',
};

// ── Persona Theme Helper ───────────────────────────────────────
function personaDisplayTheme(persona: { name: string; theme?: any } | undefined, fallbackName = 'ahri') {
  const staticTheme = getPersonaTheme(persona?.name ?? fallbackName);
  return mergePersonaTheme(staticTheme, persona?.theme);
}

function getImagePosition(name: string): string {
  return PERSONA_IMAGE_POSITIONS[name.toLowerCase().replace(/_/g, ' ')] || '50% 20%';
}

// ── Types ──────────────────────────────────────────────────────
type SettingsTab = 'api-keys' | 'chat' | 'agent' | 'instrucoes' | 'memory' | 'personas';

interface ApiKeysConfig {
  gemini_api_key_paid: string;
  gemini_api_key_free: string;
  openrouter_api_key: string;
  openrouter_model_name: string;
  google_model_flash: string;
  google_model_lite: string;
  google_model_vision: string;
  google_model_search: string;
  google_model_memory: string;
  ollama_chat_model: string;
  google_api_key_search: string;
  google_api_key_search_b: string;
  cse_api_key: string;
  cse_cx: string;
  google_api_key_vision_a: string;
  google_api_key_vision_b: string;
  google_api_key_manager: string;
  spotipy_client_id: string;
  spotipy_client_secret: string;
  spotipy_redirect_uri: string;
  google_ai_studio_api_key: string;
  deepinfra_api_key: string;
  gh_token: string;
  gist_id: string;
  // Agent Mode round-robin keys (5 keys × 15 RPM = 75 RPM)
  agent_api_key_1: string;
  agent_api_key_2: string;
  agent_api_key_3: string;
  agent_api_key_4: string;
  agent_api_key_5: string;
  agent_mode_api_model: string;
}

interface ChatConfig {
  default_engine: 'LITE' | 'DEEPSEEK' | 'LOCAL';
  streaming_enabled: boolean;
  max_history_messages: number;
  auto_save_tags: boolean;
  show_timestamps: boolean;
  compaction_threshold: number;
  compaction_recent_window: number;
  reasoning_level: string;
  internet_search_enabled?: boolean;
}

interface AgentConfig {
  agent_mode_enabled: boolean;
  orchestrator_model: string;
  ollama_base_url: string;
  auto_approve_tasks: boolean;
  max_parallel_workers: number;
  agent_mode_tpm_limit: number;
  agent_mode_rpm_limit: number;
  agent_mode_local_model: string;
  agent_mode_api_model: string;
}

interface ProfileFlattened {
  name: string;
  archetype: string;
  learning_style: string;
  bio: string;
  personality: string[];
  occupation: string;
  interests: string[];
  tech_stack: string[];
  music: string[];
  dislikes: string[];
  foods: string[];
  languages: Record<string, string>;
}

interface EditablePersona {
  displayName: string;
  description: string;
  primaryColor: string;
  secondaryColor: string;
  avatarFile?: File;
  backgroundFile?: File;
}

// Storage helpers
const STORAGE_PREFIX = 'ahri_settings_';

function loadFromStorage<T>(key: string, defaults: T): T {
  try {
    const stored = localStorage.getItem(STORAGE_PREFIX + key);
    if (stored) return { ...defaults, ...JSON.parse(stored) };
  } catch { /* ignore */ }
  return defaults;
}

function saveToStorage(key: string, data: unknown) {
  localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(data));
}

// ── Default Values ────────────────────────────────────────────
const DEFAULT_API_KEYS: ApiKeysConfig = {
  gemini_api_key_paid: '',
  gemini_api_key_free: '',
  openrouter_api_key: '',
  openrouter_model_name: 'deepseek/deepseek-r1:free',
  google_model_flash: 'gemini-2.5-flash',
  google_model_lite: 'gemini-3.1-flash-lite-preview',
  google_model_vision: 'gemini-2.5-flash',
  google_model_search: 'gemini-3.1-flash-lite-preview',
  google_model_memory: 'gemini-3.1-flash-lite-preview',
  ollama_chat_model: 'gpt-oss:20b',
  google_api_key_search: '',
  google_api_key_search_b: '',
  cse_api_key: '',
  cse_cx: '',
  google_api_key_vision_a: '',
  google_api_key_vision_b: '',
  google_api_key_manager: '',
  spotipy_client_id: '',
  spotipy_client_secret: '',
  spotipy_redirect_uri: 'http://localhost:8888/callback',
  google_ai_studio_api_key: '',
  deepinfra_api_key: '',
  gh_token: '',
  gist_id: '',
  agent_api_key_1: '',
  agent_api_key_2: '',
  agent_api_key_3: '',
  agent_api_key_4: '',
  agent_api_key_5: '',
  agent_mode_api_model: 'gemini-3.1-flash-lite-preview',
};

const DEFAULT_CHAT: ChatConfig = {
  default_engine: 'LITE',
  streaming_enabled: true,
  max_history_messages: 50,
  auto_save_tags: true,
  show_timestamps: true,
  compaction_threshold: 30,
  compaction_recent_window: 15,
  reasoning_level: 'off',
  internet_search_enabled: false,
};

const DEFAULT_AGENT: AgentConfig = {
  agent_mode_enabled: true,
  orchestrator_model: 'gemini-3.1-flash-lite-preview',
  ollama_base_url: 'http://localhost:11434',
  auto_approve_tasks: false,
  max_parallel_workers: 4,
  agent_mode_tpm_limit: 250000,
  agent_mode_rpm_limit: 15,
  agent_mode_local_model: 'qwen3:8b',
  agent_mode_api_model: 'gemini-3.1-flash-lite-preview',
};

const DEFAULT_PROFILE: ProfileFlattened = {
  name: 'Sitr3n',
  archetype: 'Humanista Melancólico',
  learning_style: 'Associação com Lore/Narrativa',
  bio: '',
  personality: [],
  occupation: '',
  interests: [
    'Anime (Violet Evergarden, Frieren, Diários de uma Apotecária)',
    'Lore de Jogos (HSR, Genshin, LoL, Valorant, WuWa)',
    'Audiofilia', 'Antropologia', 'Sociologia', 'Cosplay',
    'Hardware avançado', 'Software', 'História', 'Filosofia',
    'Aviação', 'Fotografia', 'Filmografia',
  ],
  tech_stack: ['Unity', 'Python', 'Internet'],
  music: ['MPB', 'Bossa Nova', 'Eletrônica', 'J-pop', 'K-pop', 'Orquestra', 'Lo-fi'],
  dislikes: ['Respostas secas', 'Falta de profundidade'],
  foods: [],
  languages: { 'Japanese': 'N5' },
};

// ── Main Component ────────────────────────────────────────────
export function SettingsView({ onClose }: { onClose?: () => void }) {
  const t = useT();
  const locale = useI18nStore((s) => s.locale);
  const setLocale = useI18nStore((s) => s.setLocale);

  const personas = usePersonaStore((s) => s.personas);
  const activePersona = usePersonaStore((s) => s.activePersona);
  const fetchPersonas = usePersonaStore((s) => s.fetchPersonas);
  const logout = useAuthStore((s) => s.logout);
  const appTheme = useThemeStore((s) => s.theme);
  const toggleTheme = useThemeStore((s) => s.toggleTheme);

  const [activeTab, setActiveTab] = useState<SettingsTab>('api-keys');
  const [apiKeys, setApiKeys] = useState<ApiKeysConfig>(() => loadFromStorage('api_keys', DEFAULT_API_KEYS));
  const [chatConfig, setChatConfig] = useState<ChatConfig>(() => loadFromStorage('chat', DEFAULT_CHAT));
  const [agentConfig, setAgentConfig] = useState<AgentConfig>(() => loadFromStorage('agent', DEFAULT_AGENT));
  const [userProfile, setUserProfile] = useState<ProfileFlattened>(() => loadFromStorage('profile', DEFAULT_PROFILE));
  const [savedFeedback, setSavedFeedback] = useState<string | null>(null);

  // Persona editor state
  const [selectedPersona, setSelectedPersona] = useState<string | null>(null);
  const [editedData, setEditedData] = useState<EditablePersona | null>(null);
  const [hasChanges, setHasChanges] = useState(false);

  // Auto-save prev state tracking
  const lastApiKeys = useRef<ApiKeysConfig>(apiKeys);
  const lastChatConfig = useRef<ChatConfig>(chatConfig);
  const lastAgentConfig = useRef<AgentConfig>(agentConfig);
  const lastUserProfile = useRef<ProfileFlattened>(userProfile);
  const isInitialLoad = useRef(true);

  // Load settings from API on mount
  useEffect(() => {
    const loadSettings = async () => {
      try {
        const [settings, profile] = await Promise.all([
          api.getSettings(),
          api.getProfile()
        ]);

        // Helper: pick first defined (non-null/undefined) value.
        // Unlike ||, this preserves empty strings "" as valid values.
        const pick = (...values: any[]) => {
          for (const v of values) {
            if (v !== undefined && v !== null) return v;
          }
          return '';
        };

        // Map API settings to ApiKeysConfig
        // Backend values (from .env) take priority over localStorage
        setApiKeys({
          gemini_api_key_paid: pick(settings.gemini_api_key_paid, ''),
          gemini_api_key_free: pick(settings.gemini_api_key_free, ''),
          openrouter_api_key: pick(settings.openrouter_api_key, ''),
          openrouter_model_name: pick(settings.openrouter_model_name, DEFAULT_API_KEYS.openrouter_model_name),
          google_model_flash: pick(settings.google_model_flash, DEFAULT_API_KEYS.google_model_flash),
          google_model_lite: pick(settings.google_model_lite, DEFAULT_API_KEYS.google_model_lite),
          google_model_vision: pick(settings.google_model_vision, DEFAULT_API_KEYS.google_model_vision),
          google_model_search: pick(settings.google_model_search, DEFAULT_API_KEYS.google_model_search),
          google_model_memory: pick(settings.google_model_memory, DEFAULT_API_KEYS.google_model_memory),
          ollama_chat_model: pick(settings.ollama_chat_model, DEFAULT_API_KEYS.ollama_chat_model),
          google_api_key_search: pick(settings.google_api_key_search, ''),
          google_api_key_search_b: pick(settings.google_api_key_search_b, ''),
          cse_api_key: pick(settings.cse_api_key, ''),
          cse_cx: pick(settings.cse_cx, ''),
          google_api_key_vision_a: pick(settings.google_api_key_vision_a, ''),
          google_api_key_vision_b: pick(settings.google_api_key_vision_b, ''),
          google_api_key_manager: pick(settings.google_api_key_manager, ''),
          spotipy_client_id: pick(settings.spotipy_client_id, ''),
          spotipy_client_secret: pick(settings.spotipy_client_secret, ''),
          spotipy_redirect_uri: pick(settings.spotipy_redirect_uri, DEFAULT_API_KEYS.spotipy_redirect_uri),
          google_ai_studio_api_key: pick(settings.google_ai_studio_api_key, ''),
          deepinfra_api_key: pick(settings.deepinfra_api_key, ''),
          gh_token: pick(settings.gh_token, ''),
          gist_id: pick(settings.gist_id, ''),
          agent_api_key_1: pick(settings.agent_api_key_1, ''),
          agent_api_key_2: pick(settings.agent_api_key_2, ''),
          agent_api_key_3: pick(settings.agent_api_key_3, ''),
          agent_api_key_4: pick(settings.agent_api_key_4, ''),
          agent_api_key_5: pick(settings.agent_api_key_5, ''),
          agent_mode_api_model: pick(settings.agent_mode_api_model, DEFAULT_API_KEYS.agent_mode_api_model),
        });

        // Also save to localStorage as cache
        saveToStorage('api_keys', apiKeys);

        // Map Profile preferences to ChatConfig + compaction from settings
        const prefs = profile.preferences || {};
        const chatPrefs = (prefs.chat || {}) as Record<string, any>;
        const mergedChat: ChatConfig = {
          default_engine: chatPrefs.default_engine ?? DEFAULT_CHAT.default_engine,
          streaming_enabled: chatPrefs.streaming_enabled ?? DEFAULT_CHAT.streaming_enabled,
          max_history_messages: chatPrefs.max_history_messages ?? DEFAULT_CHAT.max_history_messages,
          auto_save_tags: chatPrefs.auto_save_tags ?? DEFAULT_CHAT.auto_save_tags,
          show_timestamps: chatPrefs.show_timestamps ?? DEFAULT_CHAT.show_timestamps,
          compaction_threshold: settings.compaction_threshold ?? DEFAULT_CHAT.compaction_threshold,
          compaction_recent_window: settings.compaction_recent_window ?? DEFAULT_CHAT.compaction_recent_window,
          reasoning_level: chatPrefs.reasoning_level ?? DEFAULT_CHAT.reasoning_level,
          internet_search_enabled: chatPrefs.internet_search_enabled ?? DEFAULT_CHAT.internet_search_enabled,
        };
        setChatConfig(mergedChat);
        saveToStorage('chat', mergedChat);

        // Map Settings + Preferences to AgentConfig
        const agentPrefs = (prefs.agent || {}) as Record<string, any>;
        const mergedAgent: AgentConfig = {
          agent_mode_enabled: settings.agent_mode_enabled ?? DEFAULT_AGENT.agent_mode_enabled,
          orchestrator_model: pick(settings.agent_mode_orchestrator, DEFAULT_AGENT.orchestrator_model),
          ollama_base_url: pick(settings.ollama_base_url, DEFAULT_AGENT.ollama_base_url),
          auto_approve_tasks: agentPrefs.auto_approve_tasks ?? DEFAULT_AGENT.auto_approve_tasks,
          max_parallel_workers: settings.agent_mode_max_parallel ?? DEFAULT_AGENT.max_parallel_workers,
          agent_mode_tpm_limit: settings.agent_mode_tpm_limit ?? DEFAULT_AGENT.agent_mode_tpm_limit,
          agent_mode_rpm_limit: settings.agent_mode_rpm_limit ?? DEFAULT_AGENT.agent_mode_rpm_limit,
          agent_mode_local_model: pick(settings.agent_mode_local_model, DEFAULT_AGENT.agent_mode_local_model),
          agent_mode_api_model: pick(settings.agent_mode_api_model, DEFAULT_AGENT.agent_mode_api_model),
        };
        setAgentConfig(mergedAgent);
        saveToStorage('agent', mergedAgent);

        // Map Profile
        const mergedProfile: ProfileFlattened = {
          name: pick(profile.name, DEFAULT_PROFILE.name),
          archetype: pick(profile.archetype, DEFAULT_PROFILE.archetype),
          learning_style: pick(profile.learning_style, DEFAULT_PROFILE.learning_style),
          bio: (profile.attributes?.bio as string) ?? DEFAULT_PROFILE.bio,
          personality: (profile.attributes?.personality as string[]) ?? DEFAULT_PROFILE.personality,
          occupation: (profile.attributes?.occupation as string) ?? DEFAULT_PROFILE.occupation,
          interests: (profile.attributes?.interests as string[]) ?? DEFAULT_PROFILE.interests,
          tech_stack: (profile.attributes?.tech_stack as string[]) ?? DEFAULT_PROFILE.tech_stack,
          music: (profile.attributes?.music as string[]) ?? DEFAULT_PROFILE.music,
          dislikes: (profile.attributes?.dislikes as string[]) ?? DEFAULT_PROFILE.dislikes,
          foods: (profile.preferences?.foods as string[]) ?? DEFAULT_PROFILE.foods,
          languages: (profile.attributes?.languages as Record<string, string>) ?? DEFAULT_PROFILE.languages,
        };
        setUserProfile(mergedProfile);
        saveToStorage('profile', mergedProfile);

      } catch (e) {
        console.error('Failed to load settings from API, using localStorage cache:', e);
        // On API failure, keep the localStorage-loaded defaults (already set in useState)
        showFeedback((t('error.load_failed' as any) || 'Failed to load settings') as any);
      }
    };
    loadSettings().then(() => {
      // Delay disabling initial load flag to avoid triggering auto-saves on mount variations
      setTimeout(() => { isInitialLoad.current = false; }, 1000);
    });
  }, []);

  const currentPersona = personas.find((p) => p.name === (selectedPersona || activePersona));
  const currentTheme = personaDisplayTheme(currentPersona);

  // Initialize persona editable data
  useEffect(() => {
    if (activeTab === 'personas' && currentPersona) {
      const displayTheme = personaDisplayTheme(currentPersona);
      setEditedData({
        displayName: currentPersona.display_name,
        description: currentPersona.archetype,
        primaryColor: displayTheme.primary,
        secondaryColor: displayTheme.secondary,
      });
      setHasChanges(false);
    }
  }, [currentPersona, activeTab]);

  const showFeedback = (msg: string) => {
    setSavedFeedback(msg);
    setTimeout(() => setSavedFeedback(null), 2500);
  };

  const handleSaveApiKeys = async (): Promise<boolean> => {
    saveToStorage('api_keys', apiKeys);
    try {
      await api.updateSettings(apiKeys);
      return true;
    } catch (e) {
      console.error('Failed to save API keys:', e);
      showFeedback('Error saving API keys');
      return false;
    }
  };

  const handleSaveChatConfig = async (): Promise<boolean> => {
    try {
      // Get current profile first to not overwrite other prefs
      const profile = await api.getProfile();
      await api.saveProfile({
        ...profile,
        preferences: {
          ...profile.preferences,
          chat: chatConfig
        }
      });
      // Save compaction settings to .env via settings API
      await api.updateSettings({
        compaction_threshold: chatConfig.compaction_threshold,
        compaction_recent_window: chatConfig.compaction_recent_window,
      });
      return true;
    } catch (e) {
      console.error('Failed to save chat config:', e);
      showFeedback('Error saving chat config');
      return false;
    }
  };

  const handleSaveAgentConfig = async (): Promise<boolean> => {
    saveToStorage('agent', agentConfig);
    try {
      // 1. Save Environment Settings (all agent config to .env)
      await api.updateSettings({
        agent_mode_enabled: agentConfig.agent_mode_enabled,
        agent_mode_orchestrator: agentConfig.orchestrator_model,
        ollama_base_url: agentConfig.ollama_base_url,
        agent_mode_tpm_limit: agentConfig.agent_mode_tpm_limit,
        agent_mode_rpm_limit: agentConfig.agent_mode_rpm_limit,
        agent_mode_max_parallel: agentConfig.max_parallel_workers,
        agent_mode_local_model: agentConfig.agent_mode_local_model,
        agent_mode_api_model: agentConfig.agent_mode_api_model,
      });

      // 2. Save Profile Preferences
      const profile = await api.getProfile();
      await api.saveProfile({
        ...profile,
        preferences: {
          ...profile.preferences,
          agent: {
            auto_approve_tasks: agentConfig.auto_approve_tasks,
          }
        }
      });
      return true;
    } catch (e) {
      console.error('Failed to save agent config:', e);
      showFeedback('Error saving agent config');
      return false;
    }
  };

  const handleSaveProfile = async (): Promise<boolean> => {
    saveToStorage('profile', userProfile);
    try {
      // Construct full profile object including attributes
      const current = await api.getProfile();
      await api.saveProfile({
        ...current,
        name: userProfile.name,
        archetype: userProfile.archetype,
        learning_style: userProfile.learning_style,
        attributes: {
          ...current.attributes,
          bio: userProfile.bio,
          personality: userProfile.personality,
          occupation: userProfile.occupation,
          interests: userProfile.interests,
          tech_stack: userProfile.tech_stack,
          music: userProfile.music,
          dislikes: userProfile.dislikes,
          languages: userProfile.languages,
        },
        preferences: {
          ...current.preferences,
          foods: userProfile.foods,
        },
      });
      return true;
    } catch (e) {
      console.error('Failed to save profile:', e);
      showFeedback('Error saving profile');
      return false;
    }
  };

  // ── Auto-save Hooks ──────────────────────────────────────────
  useEffect(() => {
    const currentStr = JSON.stringify(apiKeys);
    if (currentStr !== JSON.stringify(lastApiKeys.current)) {
      // Immediate local persistence
      saveToStorage('api_keys', apiKeys);
      // Debounced server sync
      const t = setTimeout(async () => {
        if (isInitialLoad.current) return;
        const ok = await handleSaveApiKeys();
        if (ok) lastApiKeys.current = apiKeys;
      }, 1200);
      return () => clearTimeout(t);
    }
  }, [apiKeys]);

  useEffect(() => {
    const currentStr = JSON.stringify(chatConfig);
    if (currentStr !== JSON.stringify(lastChatConfig.current)) {
      // Safely register settings instantly guaranteeing they are never lost
      saveToStorage('chat', chatConfig);
      useChatStore.getState().loadChatSettings();
      // Debounce the complex server syncing
      const t = setTimeout(async () => {
        if (isInitialLoad.current) return;
        const ok = await handleSaveChatConfig();
        if (ok) lastChatConfig.current = chatConfig;
      }, 1200);
      return () => clearTimeout(t);
    }
  }, [chatConfig]);

  useEffect(() => {
    const currentStr = JSON.stringify(agentConfig);
    if (currentStr !== JSON.stringify(lastAgentConfig.current)) {
      // Immediate local persistence
      saveToStorage('agent', agentConfig);
      // Debounced server sync
      const t = setTimeout(async () => {
        if (isInitialLoad.current) return;
        const ok = await handleSaveAgentConfig();
        if (ok) lastAgentConfig.current = agentConfig;
      }, 1200);
      return () => clearTimeout(t);
    }
  }, [agentConfig]);

  useEffect(() => {
    const currentStr = JSON.stringify(userProfile);
    if (currentStr !== JSON.stringify(lastUserProfile.current)) {
      // Immediate local persistence
      saveToStorage('profile', userProfile);
      // Debounced server sync
      const t = setTimeout(async () => {
        if (isInitialLoad.current) return;
        const ok = await handleSaveProfile();
        if (ok) lastUserProfile.current = userProfile;
      }, 1200);
      return () => clearTimeout(t);
    }
  }, [userProfile]);

  const fileToBase64 = (file: File): Promise<string> => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => resolve(reader.result as string);
      reader.onerror = (error) => reject(error);
    });
  };

  const handlePersonaFieldChange = (field: keyof EditablePersona, value: string | File) => {
    if (!editedData) return;
    setEditedData({ ...editedData, [field]: value });
    setHasChanges(true);
  };

  const handlePersonaSave = async () => {
    if (!currentPersona || !editedData) return;
    try {
      const updateData: any = {
        display_name: editedData.displayName,
        archetype: editedData.description,
        primary_color: editedData.primaryColor,
        secondary_color: editedData.secondaryColor,
      };

      if (editedData.avatarFile) {
        updateData.avatar_base64 = await fileToBase64(editedData.avatarFile);
      }
      if (editedData.backgroundFile) {
        updateData.background_base64 = await fileToBase64(editedData.backgroundFile);
      }

      await api.updatePersona(currentPersona.name, updateData);
      showFeedback(locale === 'pt' ? 'Persona salva' : 'Persona saved');
      setHasChanges(false);
      await fetchPersonas();
      // Rebuild editedData from fresh store so colors reflect what was just saved
      const freshPersona = usePersonaStore.getState().personas.find(p => p.name === currentPersona.name);
      if (freshPersona) {
        const freshTheme = personaDisplayTheme(freshPersona);
        setEditedData(prev => prev ? {
          ...prev,
          primaryColor: freshTheme.primary,
          secondaryColor: freshTheme.secondary,
          avatarFile: undefined,
          backgroundFile: undefined,
        } : prev);
      }
    } catch (e) {
      console.error('Failed to save persona:', e);
      showFeedback('Error saving persona');
    }
  };

  const handlePersonaCancel = () => {
    if (currentPersona) {
      const displayTheme = personaDisplayTheme(currentPersona);
      setEditedData({
        displayName: currentPersona.display_name,
        description: currentPersona.archetype,
        primaryColor: displayTheme.primary,
        secondaryColor: displayTheme.secondary,
      });
      setHasChanges(false);
    }
  };

  // ── Tabs config ────────────────────────────────────────────
  const tabs: { id: SettingsTab; label: string; icon: React.ReactElement }[] = [
    {
      id: 'api-keys',
      label: t('tab.api_keys'),
      icon: (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 2l-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0l3 3L22 7l-3-3m-3.5 3.5L19 4" />
        </svg>
      ),
    },
    {
      id: 'chat',
      label: t('tab.chat'),
      icon: (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
      ),
    },
    {
      id: 'agent',
      label: t('tab.agent'),
      icon: (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      ),
    },
    {
      id: 'instrucoes',
      label: locale === 'pt' ? 'Instruções' : 'Instructions',
      icon: (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
          <circle cx="8.5" cy="7" r="4" />
          <line x1="20" y1="8" x2="20" y2="14" />
          <line x1="23" y1="11" x2="17" y2="11" />
        </svg>
      ),
    },
    {
      id: 'memory',
      label: locale === 'pt' ? 'Memória' : 'Memory',
      icon: (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <ellipse cx="12" cy="5" rx="9" ry="3" />
          <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
          <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
        </svg>
      ),
    },
    {
      id: 'personas',
      label: t('tab.personas'),
      icon: (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        </svg>
      ),
    },
  ];

  return (
    <div className="flex h-full w-full bg-[var(--surface-solid)] text-[var(--text-primary)] relative" style={{ background: 'var(--surface-solid)' }}>
      {onClose && (
        <button onClick={onClose} className="absolute top-6 right-6 p-2 rounded-full hover:bg-black/5 dark:hover:bg-white/10 transition-colors z-50 shadow-sm border bg-[var(--sidebar-bg)]" style={{ borderColor: 'var(--glass-border)', color: 'var(--text-secondary)' }} title={t('common.close' as any)}>
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" /></svg>
        </button>
      )}
      {/* Sidebar */}
      <aside className="w-64 flex-shrink-0 flex flex-col border-r relative z-10 shadow-sm" style={{ borderColor: 'var(--glass-border)', background: 'var(--sidebar-bg)' }}>
        {/* Sidebar Header */}
        <div className="p-6 pb-2">
          <h1
            className="text-2xl font-bold tracking-tight mb-1"
            style={{
              background: 'linear-gradient(135deg, var(--persona-primary) 0%, var(--persona-secondary) 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              backgroundClip: 'text',
            }}
          >
            {t('settings.title')}
          </h1>
          <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            {t('settings.subtitle')}
          </p>
        </div>

        {/* Sidebar Navigation */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${activeTab === tab.id ? 'active' : ''}`}
              style={activeTab === tab.id 
                ? { background: 'var(--persona-primary)', color: '#fff', boxShadow: '0 4px 12px color-mix(in srgb, var(--persona-shadow) 30%, transparent)' } 
                : { color: 'var(--text-secondary)' }
              }
            >
              {tab.icon}
              <span>{tab.label}</span>
            </button>
          ))}
        </nav>

        {/* Utilities Footer */}
        <div className="p-4 border-t flex flex-col gap-4" style={{ borderColor: 'var(--glass-border)', background: 'var(--sidebar-bg)' }}>
          {savedFeedback && (
            <div className="flex items-center gap-2 text-xs text-emerald-500 font-medium px-2 animate-fade-in">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M20 6L9 17l-5-5" /></svg>
              {savedFeedback}
            </div>
          )}
          
          <div className="flex items-center justify-between">
            <div className="flex items-center p-0.5 rounded-lg border" style={{ borderColor: 'var(--glass-border)', background: 'rgba(128, 128, 128, 0.05)' }}>
              <button 
                onClick={() => setLocale('pt')} 
                className="px-2 py-1.5 rounded-md text-[10px] font-bold uppercase transition-all" 
                style={locale === 'pt' ? { background: 'var(--persona-primary)', color: '#fff' } : { color: 'var(--text-tertiary)' }}
              >
                PT
              </button>
              <button 
                onClick={() => setLocale('en')} 
                className="px-2 py-1.5 rounded-md text-[10px] font-bold uppercase transition-all" 
                style={locale === 'en' ? { background: 'var(--persona-primary)', color: '#fff' } : { color: 'var(--text-tertiary)' }}
              >
                EN
              </button>
            </div>

            <div className="flex items-center gap-1">
              <button onClick={toggleTheme} className="p-2 rounded-lg hover:bg-black/5 dark:hover:bg-white/5 transition-colors" style={{ color: 'var(--text-secondary)' }} title={appTheme === 'dark' ? t('common.theme_light') : t('common.theme_dark')}>
                {appTheme === 'dark' ? (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41" /></svg>
                ) : (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" /></svg>
                )}
              </button>
              
              <button onClick={logout} className="p-2 rounded-lg text-red-500 hover:bg-red-500/10 transition-colors" title={t('nav.logout')}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" /></svg>
              </button>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 flex flex-col min-w-0 relative z-10 overflow-hidden">
        <div key={activeTab} className="flex-1 overflow-y-auto w-full animate-fade-in p-6 lg:p-12" style={{ animationDuration: '0.35s' }}>
          <div className="max-w-6xl w-full mx-auto pb-24">
            {activeTab === 'api-keys' && <ApiKeysTab config={apiKeys} onChange={setApiKeys} />}
            {activeTab === 'chat' && <ChatTab config={chatConfig} onChange={setChatConfig} />}
            {activeTab === 'agent' && <AgentTab config={agentConfig} onChange={setAgentConfig} />}
            {activeTab === 'instrucoes' && <InstrucoesTab />}
            {activeTab === 'memory' && <MemoryTab />}
            {activeTab === 'personas' && (
              <PersonasTab
                personas={personas}
                selectedPersona={selectedPersona}
                activePersona={activePersona}
                editedData={editedData}
                hasChanges={hasChanges}
                onSelectPersona={(name: string) => {
                  if (hasChanges && !confirm(t('persona.unsaved_confirm'))) return;
                  setSelectedPersona(name);
                  // Sync app theme immediately
                  const personaStore = usePersonaStore.getState();
                  personaStore.activatePersona(name);
                }}
                onFieldChange={handlePersonaFieldChange}
                onSave={handlePersonaSave}
                onCancel={handlePersonaCancel}
              />
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

// ── API Keys Tab ──────────────────────────────────────────────
function ApiKeysTab({
  config,
  onChange,
}: {
  config: ApiKeysConfig;
  onChange: (c: ApiKeysConfig) => void;
}) {
  const t = useT();
  const locale = useI18nStore((s) => s.locale);
  const [activeCategory, setActiveCategory] = useState<'llm' | 'agent' | 'vision' | 'integrations'>('llm');

  const updateField = (field: keyof ApiKeysConfig, value: string) => {
    onChange({ ...config, [field]: value });
  };

  const categories = [
    { id: 'llm', label: t('api.category.llm') },
    { id: 'agent', label: t('api.category.agent') },
    { id: 'vision', label: t('api.category.vision') },
    { id: 'integrations', label: t('api.category.integrations') },
  ];

  return (
    <div className="flex flex-col gap-6">
      {/* Sub Tabs */}
      <div className="flex items-center gap-2 border-b pb-4 mb-4" style={{ borderColor: 'var(--glass-border)' }}>
        {categories.map((cat) => (
          <button
            key={cat.id}
            onClick={() => setActiveCategory(cat.id as any)}
            className={`px-3 py-1.5 rounded-full text-xs font-semibold transition-all ${activeCategory === cat.id ? 'active' : ''}`}
            style={activeCategory === cat.id
              ? { background: 'var(--persona-primary)', color: '#fff', boxShadow: '0 2px 8px color-mix(in srgb, var(--persona-shadow) 40%, transparent)' }
              : { background: 'rgba(255, 255, 255, 0.03)', color: 'var(--text-tertiary)', border: '1px solid var(--glass-border)' }}
          >
            {cat.label}
          </button>
        ))}
      </div>

      <div className="space-y-6 mt-4">
        {activeCategory === 'llm' && (
          <>
            <SettingsSection title={t('api.google_gemini')} description={t('api.google_gemini_desc')}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <KeyInput label={t('api.gemini_paid')} value={config.gemini_api_key_paid} onChange={(v) => updateField('gemini_api_key_paid', v)} placeholder="AIza..." />
                <div>
                  <label className="settings-label">{t('api.model_flash' as any)}</label>
                  <input type="text" className="settings-input" value={config.google_model_flash || ''} onChange={(e) => updateField('google_model_flash', e.target.value)} placeholder="gemini-2.5-flash" />
                </div>
              </div>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                <KeyInput label={t('api.gemini_free')} value={config.gemini_api_key_free} onChange={(v) => updateField('gemini_api_key_free', v)} placeholder="AIza..." />
                <div>
                  <label className="settings-label">{t('api.model_lite' as any)}</label>
                  <input type="text" className="settings-input" value={config.google_model_lite || ''} onChange={(e) => updateField('google_model_lite', e.target.value)} placeholder="gemini-3.1-flash-lite-preview" />
                </div>
              </div>

            </SettingsSection>

            <SettingsSection title={t('api.openrouter')} description={t('api.openrouter_desc')}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <KeyInput label={t('api.openrouter_key')} value={config.openrouter_api_key} onChange={(v) => updateField('openrouter_api_key', v)} placeholder="sk-or-..." />
                <div>
                  <label className="settings-label">{t('api.model_name')}</label>
                  <input type="text" className="settings-input" value={config.openrouter_model_name} onChange={(e) => updateField('openrouter_model_name', e.target.value)} placeholder="deepseek/deepseek-r1:free" />
                </div>
              </div>
            </SettingsSection>
            
            <SettingsSection title={t('api.other')} description={t('api.other_desc')}>
              <KeyInput label={t('api.deepinfra_key')} value={config.deepinfra_api_key} onChange={(v) => updateField('deepinfra_api_key', v)} placeholder="di_..." hint={t('api.deepinfra_hint')} />
            </SettingsSection>

            <SettingsSection title={"Ollama (Local Models)"} description={locale === 'pt' ? 'Configurações de modelos open-source locais via Ollama' : 'Configuration for local open-source models via Ollama'}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="settings-label">{locale === 'pt' ? 'Modelo Primário (Chat)' : 'Primary Model (Chat)'}</label>
                  <input type="text" className="settings-input" value={config.ollama_chat_model || ''} onChange={(e) => updateField('ollama_chat_model', e.target.value)} placeholder="gpt-oss:20b" />
                </div>
              </div>
            </SettingsSection>

            <SettingsSection title={t('api.memory_manager')} description={t('api.memory_manager_desc')}>
              <KeyInput label={t('api.memory_manager_key')} value={config.google_api_key_manager} onChange={(v) => updateField('google_api_key_manager', v)} placeholder="AIza..." hint={t('api.memory_manager_hint')} />
              <div className="mt-4">
                <label className="settings-label">{locale === 'pt' ? 'Modelo Exato de Memória' : 'Exact Memory Model'}</label>
                <input 
                  type="text" 
                  className="settings-input" 
                  value={config.google_model_memory || ''} 
                  onChange={(e) => updateField('google_model_memory', e.target.value)} 
                  placeholder="gemini-3.1-flash-lite-preview" 
                />
                <p className="text-[10px] mt-1 pr-2 leading-tight" style={{ color: 'var(--text-tertiary)' }}>
                  {locale === 'pt' ? 'Modelo para compactação de histórico e extração de fatos (Background).' : 'Model for history compaction and fact extraction (Background).'}
                </p>
              </div>
            </SettingsSection>

            <ModelTesterSection apiKey={config.gemini_api_key_paid || config.google_ai_studio_api_key} />
          </>
        )}

        {activeCategory === 'agent' && (
           <SettingsSection title="Agent Mode Keys (Round-Robin)" description="Up to 6 API keys × 15 RPM = 90 RPM total. Add Gemini API keys for agent mode to increase throughput.">
             <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
               {[1, 2, 3, 4, 5].map((n) => (
                 <KeyInput
                   key={`agent_key_${n}`}
                   label={`Agent Key ${n}`}
                   value={config[`agent_api_key_${n}` as keyof ApiKeysConfig]}
                   onChange={(v) => updateField(`agent_api_key_${n}` as keyof ApiKeysConfig, v)}
                   placeholder="AIza..."
                   hint={n === 1 ? 'Primary agent key (required for agent mode)' : undefined}
                 />
               ))}
               <KeyInput
                 label="Agent Key 6 (AI Studio)"
                 value={config.google_ai_studio_api_key}
                 onChange={(v) => updateField('google_ai_studio_api_key', v)}
                 placeholder="AIza..."
                 hint="Additional key from AI Studio (free tier)"
               />
             </div>
           </SettingsSection>
        )}

        {activeCategory === 'vision' && (
          <>
            <SettingsSection title={t('api.google_search')} description={t('api.google_search_desc')}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <KeyInput label={t('api.cse_key')} value={config.cse_api_key} onChange={(v) => updateField('cse_api_key', v)} placeholder="AIza..." />
                <div>
                  <label className="settings-label">{t('api.cse_cx')}</label>
                  <input type="text" className="settings-input" value={config.cse_cx} onChange={(e) => updateField('cse_cx', e.target.value)} placeholder="abc123:xyz" />
                </div>
                <KeyInput label={t('api.search_key_a')} value={config.google_api_key_search} onChange={(v) => updateField('google_api_key_search', v)} placeholder="AIza..." />
                <KeyInput label={t('api.search_key_b')} value={config.google_api_key_search_b} onChange={(v) => updateField('google_api_key_search_b', v)} placeholder="AIza..." hint={t('api.backup_key_hint')} />
                <div className="md:col-span-2 mt-2">
                  <label className="settings-label">{locale === 'pt' ? 'Modelo Exato de Busca (Síntese)' : 'Exact Search Model (Synthesis)'}</label>
                  <input 
                    type="text" 
                    className="settings-input" 
                    value={config.google_model_search || ''} 
                    onChange={(e) => updateField('google_model_search', e.target.value)} 
                    placeholder="gemini-3.1-flash-lite-preview" 
                  />
                  <p className="text-[10px] mt-1 pr-2 leading-tight" style={{ color: 'var(--text-tertiary)' }}>
                    {locale === 'pt' ? 'Modelo para sintetizar resultados de busca na web.' : 'Model for synthesizing web search results.'}
                  </p>
                </div>
              </div>
            </SettingsSection>

            <SettingsSection title={t('api.vision')} description={t('api.vision_desc')}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <KeyInput label={t('api.vision_key_a')} value={config.google_api_key_vision_a} onChange={(v) => updateField('google_api_key_vision_a', v)} placeholder="AIza..." />
                <KeyInput label={t('api.vision_key_b')} value={config.google_api_key_vision_b} onChange={(v) => updateField('google_api_key_vision_b', v)} placeholder="AIza..." hint={t('api.backup_key_hint')} />
                <div className="md:col-span-2 mt-2">
                  <label className="settings-label">{locale === 'pt' ? 'Modelo Exato de Visão' : 'Exact Vision Model'}</label>
                  <input 
                    type="text" 
                    className="settings-input" 
                    value={config.google_model_vision || ''} 
                    onChange={(e) => updateField('google_model_vision', e.target.value)} 
                    placeholder="gemini-2.5-flash" 
                  />
                  <p className="text-[10px] mt-1 pr-2 leading-tight" style={{ color: 'var(--text-tertiary)' }}>
                    {locale === 'pt' ? 'Modelo para análise de imagens e OCR no Modo Agente.' : 'Model for image analysis and OCR in Agent Mode.'}
                  </p>
                </div>
              </div>
            </SettingsSection>

            <SettingsSection title={t('api.memory_manager')} description={t('api.memory_manager_desc')}>
              <KeyInput label={t('api.memory_manager_key')} value={config.google_api_key_manager} onChange={(v) => updateField('google_api_key_manager', v)} placeholder="AIza..." hint={t('api.memory_manager_hint')} />
              <div className="mt-4">
                <label className="settings-label">{locale === 'pt' ? 'Modelo Exato de Memória' : 'Exact Memory Model'}</label>
                <input 
                  type="text" 
                  className="settings-input" 
                  value={config.google_model_memory || ''} 
                  onChange={(e) => updateField('google_model_memory', e.target.value)} 
                  placeholder="gemini-3.1-flash-lite-preview" 
                />
                <p className="text-[10px] mt-1 pr-2 leading-tight" style={{ color: 'var(--text-tertiary)' }}>
                  {locale === 'pt' ? 'Modelo para análise e síntese de memória.' : 'Model for memory analysis and synthesis.'}
                </p>
              </div>
            </SettingsSection>
          </>
        )}

        {activeCategory === 'integrations' && (
          <>
            <SettingsSection title={t('api.spotify')} description={t('api.spotify_desc')}>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <KeyInput label={t('api.client_id')} value={config.spotipy_client_id} onChange={(v) => updateField('spotipy_client_id', v)} placeholder="your-spotify-client-id" />
                <KeyInput label={t('api.client_secret')} value={config.spotipy_client_secret} onChange={(v) => updateField('spotipy_client_secret', v)} placeholder="your-spotify-client-secret" />
              </div>
              <div className="mt-4">
                <label className="settings-label">{t('api.redirect_uri')}</label>
                <input type="text" className="settings-input" value={config.spotipy_redirect_uri} onChange={(e) => updateField('spotipy_redirect_uri', e.target.value)} />
              </div>
            </SettingsSection>
            
            <SettingsSection title="GitHub & Gist" description="Tokens for saving code or accessing remote repositories.">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <KeyInput label={t('api.github_token')} value={config.gh_token} onChange={(v) => updateField('gh_token', v)} placeholder="ghp_..." hint={t('api.github_hint')} />
                <div>
                  <label className="settings-label">{t('api.gist_id')}</label>
                  <input type="text" className="settings-input" value={config.gist_id} onChange={(e) => updateField('gist_id', e.target.value)} placeholder="abc123..." />
                </div>
              </div>
            </SettingsSection>
          </>
        )}
      </div>
    </div>
  );
}

// ── Chat Settings Tab ─────────────────────────────────────────
function ChatTab({
  config,
  onChange,
}: {
  config: ChatConfig;
  onChange: (c: ChatConfig) => void;
}) {
  const t = useT();
  const locale = useI18nStore((s) => s.locale);

  return (
    <div className="flex flex-col gap-6">
      {/* Settings Panel for Motor/Engine was removed because the user sets this dynamically straight from ChatInput UI */}

      <SettingsSection title={t('chat.behavior')} description={t('chat.behavior_desc')}>
        <SettingsToggle label={t('chat.streaming')} description={t('chat.streaming_desc')} checked={config.streaming_enabled} onChange={(v) => onChange({ ...config, streaming_enabled: v })} />
        <SettingsToggle label={t('chat.auto_tags')} description={t('chat.auto_tags_desc')} checked={config.auto_save_tags} onChange={(v) => onChange({ ...config, auto_save_tags: v })} />
        <SettingsToggle label={t('chat.timestamps')} description={t('chat.timestamps_desc')} checked={config.show_timestamps} onChange={(v) => onChange({ ...config, show_timestamps: v })} />
        {/* Reasoning level — 4-option segmented control */}
        <div className="flex flex-col gap-2 py-3 border-b" style={{ borderColor: 'var(--glass-border)' }}>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                {locale === 'pt' ? 'Nível de Raciocínio' : 'Reasoning Level'}
              </p>
              <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
                {locale === 'pt' ? 'Thinking budget para modelos Google (Gemini Flash Lite, Flash, Pro)' : 'Thinking budget for Google models (Gemini Flash Lite, Flash, Pro)'}
              </p>
            </div>
          </div>
          <div className="flex gap-1 mt-1">
            {(['off', 'low', 'medium', 'high'] as const).map((level) => {
              const labels: Record<string, string> = {
                off: locale === 'pt' ? 'Desativado' : 'Off',
                low: locale === 'pt' ? 'Baixo' : 'Low',
                medium: locale === 'pt' ? 'Médio' : 'Medium',
                high: locale === 'pt' ? 'Alto' : 'High',
              };
              const isActive = (config.reasoning_level || 'off') === level;
              return (
                <button
                  key={level}
                  onClick={() => onChange({ ...config, reasoning_level: level })}
                  className="flex-1 px-2 py-1.5 rounded-lg text-xs font-medium transition-all"
                  style={{
                    background: isActive ? 'var(--persona-primary)' : 'var(--glass-bg)',
                    color: isActive ? '#fff' : 'var(--text-secondary)',
                    border: `1px solid ${isActive ? 'var(--persona-primary)' : 'var(--glass-border)'}`,
                  }}
                >
                  {labels[level]}
                </button>
              );
            })}
          </div>
        </div>
        <SettingsToggle label={t('chat.web_search')} description={t('chat.web_search_desc')} checked={config.internet_search_enabled || false} onChange={(v) => onChange({ ...config, internet_search_enabled: v })} />
      </SettingsSection>

      {/* Legacy History section removed. Relying solely on Compaction Service algorithms dynamically. */}

      <SettingsSection
        title={t('chat.compaction')}
        description={t('chat.compaction_desc')}
      >
        <div className="space-y-4">
          <div>
            <label className="settings-label">{t('chat.compaction_threshold')}</label>
            <input type="number" className="settings-input" value={config.compaction_threshold} onChange={(e) => onChange({ ...config, compaction_threshold: Number(e.target.value) })} min={10} max={200} step={5} />
            <p className="text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>
              {t('chat.compaction_threshold_desc')}
            </p>
          </div>
          <div>
            <label className="settings-label">{t('chat.compaction_window')}</label>
            <input type="number" className="settings-input" value={config.compaction_recent_window} onChange={(e) => onChange({ ...config, compaction_recent_window: Number(e.target.value) })} min={5} max={100} step={5} />
            <p className="text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>
              {t('chat.compaction_window_desc')}
            </p>
          </div>
          
          <div className="pt-2 border-t" style={{ borderColor: 'var(--glass-border)' }}>
            <p className="text-[10px] leading-tight flex items-center gap-1.5" style={{ color: 'var(--text-tertiary)' }}>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="16" x2="12" y2="12" />
                <line x1="12" y1="8" x2="12.01" y2="8" />
              </svg>
              {t('chat.compaction_model_hint')}
            </p>
          </div>
        </div>
      </SettingsSection>

    </div>
  );
}

// ── Agent Settings Tab ────────────────────────────────────────
function AgentTab({
  config,
  onChange,
}: {
  config: AgentConfig;
  onChange: (c: AgentConfig) => void;
}) {
  const t = useT();
  const locale = useI18nStore((s) => s.locale);

  return (
    <div className="flex flex-col gap-6">
      <SettingsSection title={t('agent.general')} description={t('agent.general_desc')}>
        <SettingsToggle label={t('agent.enabled')} description={t('agent.enabled_desc')} checked={config.agent_mode_enabled} onChange={(v) => onChange({ ...config, agent_mode_enabled: v })} />
        <SettingsToggle label={t('agent.auto_approve')} description={t('agent.auto_approve_desc')} checked={config.auto_approve_tasks} onChange={(v) => onChange({ ...config, auto_approve_tasks: v })} />
      </SettingsSection>

      <SettingsSection title={t('agent.orchestrator')} description={t('agent.orchestrator_desc')}>
        <div>
          <label className="settings-label">{t('agent.orchestrator_model')}</label>
          <input type="text" className="settings-input" value={config.orchestrator_model || ''} onChange={(e) => onChange({ ...config, orchestrator_model: e.target.value })} placeholder="gemini-3.1-flash-lite-preview" />
          <p className="text-[10px] mt-1 pr-2 leading-tight" style={{ color: 'var(--text-tertiary)' }}>
            {t('agent.orchestrator_desc')}
          </p>
        </div>
      </SettingsSection>

      <SettingsSection
        title={t('agent.api_model')}
        description={t('agent.api_model_desc')}
      >
        <div>
          <label className="settings-label">{t('agent.api_model')}</label>
          <input type="text" className="settings-input" value={config.agent_mode_api_model} onChange={(e) => onChange({ ...config, agent_mode_api_model: e.target.value })} placeholder="gemini-3.1-flash-lite-preview" />
          <p className="text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>
            {t('agent.api_model_desc')}
          </p>
        </div>
        <div>
          <label className="settings-label">{t('agent.local_model')}</label>
          <input type="text" className="settings-input" value={config.agent_mode_local_model} onChange={(e) => onChange({ ...config, agent_mode_local_model: e.target.value })} placeholder="qwen3:8b" />
          <p className="text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>
            {t('agent.local_model_desc')}
          </p>
        </div>
      </SettingsSection>

      <SettingsSection
        title={t('agent.limits')}
        description={t('agent.limits_desc')}
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="settings-label">{t('agent.tpm_limit')}</label>
            <input type="number" className="settings-input" value={config.agent_mode_tpm_limit} onChange={(e) => onChange({ ...config, agent_mode_tpm_limit: Number(e.target.value) })} min={10000} max={1000000} step={10000} />
            <p className="text-[10px] mt-1 pr-2 leading-tight" style={{ color: 'var(--text-tertiary)' }}>
              {t('agent.tpm_limit_hint')}
            </p>
          </div>
          <div>
            <label className="settings-label">{t('agent.rpm_limit')}</label>
            <input type="number" className="settings-input" value={config.agent_mode_rpm_limit} onChange={(e) => onChange({ ...config, agent_mode_rpm_limit: Number(e.target.value) })} min={1} max={100} />
            <p className="text-[10px] mt-1 pr-2 leading-tight" style={{ color: 'var(--text-tertiary)' }}>
              {t('agent.rpm_limit_hint')}
            </p>
          </div>
          <div>
            <label className="settings-label">{t('agent.max_workers')}</label>
            <input type="number" className="settings-input" value={config.max_parallel_workers} onChange={(e) => onChange({ ...config, max_parallel_workers: Number(e.target.value) })} min={1} max={20} />
            <p className="text-[10px] mt-1 pr-2 leading-tight" style={{ color: 'var(--text-tertiary)' }}>{t('agent.max_workers_hint')}</p>
          </div>
        </div>
        <div className="mt-4">
          <label className="settings-label">{t('agent.ollama_url')}</label>
          <input type="text" className="settings-input" value={config.ollama_base_url} onChange={(e) => onChange({ ...config, ollama_base_url: e.target.value })} placeholder="http://localhost:11434" />
          <p className="text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>{t('agent.ollama_hint')}</p>
        </div>
      </SettingsSection>

      <SettingsSection
        title={t('agent.available_workers')}
        description={t('agent.available_workers_desc')}
      >
        <div className="settings-workers-grid">
          {[
            { name: 'RAG', icon: Database, key: 'worker.rag' as const },
            { name: 'Code', icon: Code, key: 'worker.code' as const },
            { name: 'Shell', icon: Terminal, key: 'worker.shell' as const },
            { name: 'Memory', icon: Brain, key: 'worker.memory' as const },
            { name: 'Web', icon: Globe, key: 'worker.web' as const },
            { name: 'Vision', icon: Eye, key: 'worker.vision' as const },
            { name: 'Browser', icon: Layout, key: 'worker.browser' as const },
            { name: 'Router', icon: Network, key: 'worker.router' as const },
            { name: 'Search', icon: Search, key: 'worker.search' as const },
          ].map((w) => (
            <div key={w.name} className="settings-worker-card">
              <div className="settings-worker-icon">
                <w.icon size={16} />
              </div>
              <div>
                <p className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>{w.name}</p>
                <p className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>{t(w.key as any)}</p>
              </div>
            </div>
          ))}
        </div>
      </SettingsSection>

    </div>
  );
}

// ── Profile Tab ───────────────────────────────────────────────
function ProfileTab({
  config,
  onChange,
}: {
  config: ProfileFlattened;
  onChange: (c: ProfileFlattened) => void;
}) {
  const t = useT();
  const locale = useI18nStore((s) => s.locale);
  const [showAdvanced, setShowAdvanced] = useState(false);

  return (
    <div className="flex flex-col gap-8 pb-10">
      {/* Identity Card */}
      <div className="settings-section-card p-6 rounded-2xl border border-[var(--glass-border)] bg-[var(--surface-solid)] relative overflow-hidden">
        <div className="absolute top-0 right-0 p-8 opacity-[0.03] pointer-events-none">
          <User size={120} />
        </div>
        
        <h3 className="text-sm font-semibold mb-6 flex items-center gap-2 text-[var(--text-primary)]">
          <User size={16} className="text-purple-400" />
          {t('profile.identity')}
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-1.5">
            <label className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-tertiary)]">{t('profile.name')}</label>
            <input
              type="text"
              className="settings-input w-full"
              value={config.name}
              onChange={(e) => onChange({ ...config, name: e.target.value })}
              placeholder="Ex: Sitr3n"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-tertiary)]">{t('profile.archetype')}</label>
            <input
              type="text"
              className="settings-input w-full"
              value={config.archetype}
              onChange={(e) => onChange({ ...config, archetype: e.target.value })}
              placeholder="Ex: Humanista"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-tertiary)]">
              {locale === 'pt' ? 'Ocupação' : 'Occupation'}
            </label>
            <input
              type="text"
              className="settings-input w-full"
              value={config.occupation}
              onChange={(e) => onChange({ ...config, occupation: e.target.value })}
              placeholder={locale === 'pt' ? 'Ex: Desenvolvedor, Estudante' : 'Ex: Developer, Student'}
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-tertiary)]">{t('profile.learning_style')}</label>
            <input
              type="text"
              className="settings-input w-full"
              value={config.learning_style}
              onChange={(e) => onChange({ ...config, learning_style: e.target.value })}
            />
          </div>
          <div className="col-span-full space-y-1.5">
            <label className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-tertiary)]">
              {locale === 'pt' ? 'Sobre Mim' : 'About Me'}
            </label>
            <textarea
              className="settings-input w-full min-h-[80px] resize-none"
              value={config.bio}
              onChange={(e) => onChange({ ...config, bio: e.target.value })}
              placeholder={locale === 'pt' ? 'Uma breve descrição sobre você...' : 'A brief description about yourself...'}
            />
          </div>
        </div>

        {/* Personality Traits */}
        <div className="mt-6">
          <label className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-tertiary)] mb-2 block">
            {locale === 'pt' ? 'Traços de Personalidade' : 'Personality Traits'}
          </label>
          <TagInput
            tags={config.personality}
            onChange={(tags) => onChange({ ...config, personality: tags })}
            placeholder={locale === 'pt' ? 'Ex: introvertido, criativo, curioso...' : 'Ex: introverted, creative, curious...'}
          />
        </div>
      </div>

      {/* Preferences & Interests Card */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="settings-section-card p-6 rounded-2xl border border-[var(--glass-border)] bg-[var(--surface-solid)]">
          <h3 className="text-sm font-semibold mb-6 flex items-center gap-2 text-[var(--text-primary)]">
            <Brain size={16} className="text-blue-400" />
            {t('profile.interests')}
          </h3>
          <TagInput 
            tags={config.interests} 
            onChange={(tags) => onChange({ ...config, interests: tags })}
            placeholder={t('profile.interests_hint')}
          />
        </div>

        <div className="settings-section-card p-6 rounded-2xl border border-[var(--glass-border)] bg-[var(--surface-solid)]">
          <h3 className="text-sm font-semibold mb-6 flex items-center gap-2 text-[var(--text-primary)]">
            <Terminal size={16} className="text-emerald-400" />
            {t('profile.tech_stack')}
          </h3>
          <TagInput 
            tags={config.tech_stack} 
            onChange={(tags) => onChange({ ...config, tech_stack: tags })}
            placeholder={t('profile.tech_stack_hint')}
          />
        </div>

        <div className="settings-section-card p-6 rounded-2xl border border-[var(--glass-border)] bg-[var(--surface-solid)]">
          <h3 className="text-sm font-semibold mb-6 flex items-center gap-2 text-[var(--text-primary)]">
            <Activity size={16} className="text-pink-400" />
            {t('profile.music_preferences')}
          </h3>
          <TagInput 
            tags={config.music} 
            onChange={(tags) => onChange({ ...config, music: tags })}
            placeholder={t('profile.music_hint')}
          />
        </div>

        <div className="settings-section-card p-6 rounded-2xl border border-[var(--glass-border)] bg-[var(--surface-solid)]">
          <h3 className="text-sm font-semibold mb-6 flex items-center gap-2 text-[var(--text-primary)]">
            <X size={16} className="text-red-400" />
            {t('profile.dislikes')}
          </h3>
          <TagInput
            tags={config.dislikes}
            onChange={(tags) => onChange({ ...config, dislikes: tags })}
            placeholder={t('profile.dislikes_hint')}
          />
        </div>

        <div className="settings-section-card p-6 rounded-2xl border border-[var(--glass-border)] bg-[var(--surface-solid)]">
          <h3 className="text-sm font-semibold mb-6 flex items-center gap-2 text-[var(--text-primary)]">
            <Sparkles size={16} className="text-orange-400" />
            {locale === 'pt' ? 'Comidas Favoritas' : 'Favorite Foods'}
          </h3>
          <TagInput
            tags={config.foods}
            onChange={(tags) => onChange({ ...config, foods: tags })}
            placeholder={locale === 'pt' ? 'Ex: sushi, pizza, açaí...' : 'Ex: sushi, pizza, pasta...'}
          />
        </div>
      </div>

      {/* Languages Section */}
      <div className="settings-section-card p-6 rounded-2xl border border-[var(--glass-border)] bg-[var(--surface-solid)]">
        <h3 className="text-sm font-semibold mb-6 flex items-center gap-2 text-[var(--text-primary)]">
          <Globe size={16} className="text-amber-400" />
          {t('profile.languages')}
        </h3>
        <div className="space-y-3">
          {Object.entries(config.languages).map(([lang, level]) => (
            <div key={lang} className="flex items-center gap-3">
              <input
                type="text"
                className="settings-input flex-1"
                value={lang}
                onChange={(e) => {
                  const newLangs = { ...config.languages };
                  delete newLangs[lang];
                  newLangs[e.target.value] = level;
                  onChange({ ...config, languages: newLangs });
                }}
                placeholder="Ex: Japanese"
              />
              <input
                type="text"
                className="settings-input w-24"
                value={level}
                onChange={(e) => {
                  const newLangs = { ...config.languages };
                  newLangs[lang] = e.target.value;
                  onChange({ ...config, languages: newLangs });
                }}
                placeholder="Ex: N5"
              />
              <button
                onClick={() => {
                  const newLangs = { ...config.languages };
                  delete newLangs[lang];
                  onChange({ ...config, languages: newLangs });
                }}
                className="p-2 rounded-lg hover:bg-red-500/10 text-red-400 transition-colors"
                title="Remove"
              >
                <X size={14} />
              </button>
            </div>
          ))}
          <button
            onClick={() => {
              const newLangs = { ...config.languages, '': '' };
              onChange({ ...config, languages: newLangs });
            }}
            className="flex items-center gap-2 text-[10px] font-semibold text-amber-400/80 hover:text-amber-400 transition-colors px-2 py-1"
          >
            <Plus size={12} />
            {locale === 'pt' ? 'Adicionar idioma' : 'Add language'}
          </button>
        </div>
      </div>

      {/* Advanced File Editor Toggle */}
      <div className="mt-4 pt-6 border-t border-[var(--glass-border)]">
        <button
          onClick={() => setShowAdvanced(!showAdvanced)}
          className="flex items-center gap-2 text-[10px] font-mono text-[var(--text-tertiary)] hover:text-[var(--text-primary)] transition-colors"
        >
          <Code size={12} />
          {showAdvanced 
            ? (locale === 'pt' ? 'Esconder Editor Avançado' : 'Hide Advanced Editor')
            : (locale === 'pt' ? 'Modo de Edição Avançada (JSON)' : 'Advanced Editing Mode (JSON)')}
        </button>
        
        {showAdvanced && (
          <div className="mt-4">
            <ProfileFilesPanel 
              config={config} 
              onSync={onChange} 
            />
          </div>
        )}
      </div>
    </div>
  );
}

// ── Personas Tab ───────────────────────────────────────────────
  function PersonasTab({
  personas,
  activePersona,
  selectedPersona,
  onSelectPersona,
  onSave,
  onCancel,
  onFieldChange,
  editedData,
  hasChanges
}: PersonasTabProps) {
  const t = useT();
  const [activePicker, setActivePicker] = useState<'primary' | 'secondary' | null>(null);
  const primaryInputRef = useRef<HTMLInputElement>(null);
  const secondaryInputRef = useRef<HTMLInputElement>(null);
  const currentPersona = personas.find((p: any) => p.name === (selectedPersona || activePersona));
  const currentTheme = personaDisplayTheme(currentPersona, 'ahri');
  const personaName = currentPersona?.name || activePersona;

  const previewTheme = editedData
    ? { ...currentTheme, primary: editedData.primaryColor, secondary: editedData.secondaryColor }
    : currentTheme;

  return (
    <div className="flex h-full">
      {/* Persona list */}
      <aside className="w-72 border-r flex flex-col flex-shrink-0" style={{ borderColor: 'var(--glass-border)' }}>
        <div className="p-4 border-b flex items-center justify-between" style={{ borderColor: 'var(--glass-border)' }}>
          <p className="text-xs font-bold uppercase tracking-wider opacity-60" style={{ color: 'var(--text-primary)' }}>
            {personas.length} {t('persona.count')}
          </p>
          <button
            className="p-1.5 rounded-lg hover:bg-[var(--surface-hover)] transition-all border border-transparent hover:border-[var(--glass-border)]"
            title="Criar nova persona"
            style={{ color: 'var(--text-primary)' }}
          >
            <Plus size={16} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto settings-persona-list custom-scrollbar">
          {personas.map((p: any) => {
            const isSelected = selectedPersona === p.name || (!selectedPersona && p.name === activePersona);
            const pTheme = personaDisplayTheme(p);
            return (
              <button
                key={p.name}
                onClick={() => onSelectPersona(p.name)}
                className={`settings-persona-card ${isSelected ? 'active' : ''}`}
                style={{ '--persona-color': pTheme.primary } as React.CSSProperties}
              >
                {isSelected && <div className="settings-persona-active-indicator" />}
                <div className="settings-persona-image-container">
                  <img
                    src={`/${pTheme.background}`}
                    alt={p.display_name}
                    className="settings-persona-image"
                    style={{ objectPosition: getImagePosition(p.name) }}
                    draggable={false}
                  />
                  <div className="settings-persona-overlay" />
                  <div className="settings-persona-info">
                    <span className="settings-persona-name truncate">{p.display_name}</span>
                    <span className="settings-persona-id truncate opacity-70">@{p.name}</span>
                  </div>
                </div>
              </button>
            );
          })}
        </div>
      </aside>

      {/* Editor */}
      <div className="flex-1 overflow-y-auto px-8 py-6 pb-32 relative custom-scrollbar">
        {currentPersona && editedData ? (
          <div className="max-w-3xl mx-auto">
            {/* Persona Premium Header (Banner) */}
            <div className="mb-8 rounded-3xl overflow-hidden border border-[var(--glass-border)] bg-[var(--glass-bg)] shadow-2xl relative group h-48 sm:h-56">
              <img
                src={`/${currentTheme.background}`}
                alt=""
                className="w-full h-full object-cover transition-transform duration-700 group-hover:scale-105"
                style={{ objectPosition: getImagePosition(currentPersona.name) }}
              />
              <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent" />

              <div className="absolute bottom-0 left-0 right-0 p-6 flex items-end gap-4">
                <div className="w-20 h-20 rounded-2xl overflow-hidden border-4 border-white/10 shadow-xl backdrop-blur-md flex-shrink-0">
                  <img src={`/${currentTheme.avatar}`} alt="" className="w-full h-full object-cover" />
                </div>
                <div className="flex-1 pb-1">
                  <div className="flex items-center gap-2">
                    <h2 className="text-2xl font-bold text-white tracking-tight drop-shadow-lg">
                      {editedData.displayName}
                    </h2>
                    {hasChanges && (
                      <span className="flex items-center gap-1.5 px-2.5 py-1 text-[10px] bg-amber-500/20 text-amber-400 border border-amber-500/30 rounded-full font-bold backdrop-blur-md animate-pulse">
                        <Sparkles size={10} />
                        {t('persona.unsaved')}
                      </span>
                    )}
                  </div>
                  <p className="text-xs font-mono text-white/60 mt-1">@{currentPersona.name}</p>
                </div>

                <button
                  className="p-2.5 rounded-xl bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/20 transition-all mb-1"
                  title="Excluir persona"
                >
                  <Trash2 size={18} />
                </button>
              </div>
            </div>

            <div className="settings-unified-container">
              {/* Basic info */}
              <div className="settings-unified-section">
                <div className="settings-unified-section-header">
                  <User size={20} className="text-[#8B5CF6]" />
                  <div>
                    <h3 className="settings-unified-section-title">{t('persona.basic_info')}</h3>
                    <p className="settings-unified-section-desc">{t('persona.basic_info_desc')}</p>
                  </div>
                </div>
                <div className="settings-inner-grid">
                  <div>
                    <label className="settings-label">{t('persona.display_name')}</label>
                    <input
                      type="text"
                      className="settings-input"
                      value={editedData.displayName}
                      onChange={(e) => onFieldChange('displayName', e.target.value)}
                    />
                  </div>
                </div>
              </div>

              {/* Persona Lore/Files section */}
              <div className="settings-unified-section">
                <div className="settings-unified-section-header">
                  <BookOpen size={20} className="text-[#EC4899]" />
                  <div>
                    <h3 className="settings-unified-section-title">{t('persona.files')}</h3>
                    <p className="settings-unified-section-desc">{t('persona.files_desc')}</p>
                  </div>
                </div>
                <PersonaFilesPanel
                  personaName={personaName}
                  basePath={`data/personas/${personaName}`}
                />
              </div>

              {/* Assets */}
              <div className="settings-unified-section">
                <div className="settings-unified-section-header">
                  <ImageIcon size={20} className="text-[#10B981]" />
                  <div>
                    <h3 className="settings-unified-section-title">{t('persona.assets')}</h3>
                    <p className="settings-unified-section-desc">{t('persona.assets_desc')}</p>
                  </div>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
                  <ImageUpload
                    label={t('persona.avatar')}
                    currentImage={currentTheme.avatar}
                    onImageSelect={(file) => onFieldChange('avatarFile', file)}
                    previewShape="circle"
                    previewSize={{ width: 64, height: 64 }}
                  />
                  <ImageUpload
                    label={t('persona.background')}
                    currentImage={currentTheme.background}
                    onImageSelect={(file) => onFieldChange('backgroundFile', file)}
                    previewShape="rectangle"
                    previewSize={{ width: 140, height: 80 }}
                  />
                </div>
              </div>

              {/* Theme colors */}
              <div className="settings-unified-section">
                <div className="settings-unified-section-header">
                  <Palette size={20} className="text-[#F59E0B]" />
                  <div>
                    <h3 className="settings-unified-section-title">{t('persona.theme_colors')}</h3>
                    <p className="settings-unified-section-desc">{t('persona.theme_colors_desc')}</p>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-6">
                  <div className="p-4 rounded-2xl bg-[var(--surface-hover)] border border-[var(--glass-border)] transition-colors hover:bg-white/[0.03]">
                    <label className="settings-label mb-3">{t('persona.primary')}</label>
                    <div className="flex items-center gap-3">
                      <div className="relative">
                        <button
                          onMouseDown={(e) => e.stopPropagation()}
                          onClick={() => {
                            if (activePicker === 'primary') {
                              setActivePicker(null);
                            } else {
                              setActivePicker('primary');
                            }
                          }}
                          className={`w-12 h-12 rounded-xl border-2 cursor-pointer shadow-lg overflow-hidden transition-all duration-300 ${activePicker === 'primary' ? 'scale-110 border-white/40 ring-4 ring-white/5' : 'border-white/10 hover:border-white/20'}`}
                          style={{ backgroundColor: editedData.primaryColor }}
                        />
                        {activePicker === 'primary' && (
                          <ColorPicker 
                            color={editedData.primaryColor}
                            onChange={(hex) => onFieldChange('primaryColor', hex)}
                            onClose={() => setActivePicker(null)}
                          />
                        )}
                      </div>
                      <input
                        type="text"
                        className="settings-input flex-1 font-mono text-sm uppercase text-center"
                        value={editedData.primaryColor}
                        onChange={(e) => { if (/^#[0-9A-Fa-f]{0,6}$/.test(e.target.value)) onFieldChange('primaryColor', e.target.value); }}
                        maxLength={7}
                      />
                    </div>
                  </div>
                  <div className="p-4 rounded-2xl bg-[var(--surface-hover)] border border-[var(--glass-border)] transition-colors hover:bg-white/[0.03]">
                    <label className="settings-label mb-3">{t('persona.secondary')}</label>
                    <div className="flex items-center gap-3">
                      <div className="relative">
                        <button
                          onMouseDown={(e) => e.stopPropagation()}
                          onClick={() => {
                            if (activePicker === 'secondary') {
                              setActivePicker(null);
                            } else {
                              setActivePicker('secondary');
                            }
                          }}
                          className={`w-12 h-12 rounded-xl border-2 cursor-pointer shadow-lg overflow-hidden transition-all duration-300 ${activePicker === 'secondary' ? 'scale-110 border-white/40 ring-4 ring-white/5' : 'border-white/10 hover:border-white/20'}`}
                          style={{ backgroundColor: editedData.secondaryColor }}
                        />
                        {activePicker === 'secondary' && (
                          <ColorPicker 
                            color={editedData.secondaryColor}
                            onChange={(hex) => onFieldChange('secondaryColor', hex)}
                            onClose={() => setActivePicker(null)}
                          />
                        )}
                      </div>
                      <input
                        type="text"
                        className="settings-input flex-1 font-mono text-sm uppercase text-center"
                        value={editedData.secondaryColor}
                        onChange={(e) => { if (/^#[0-9A-Fa-f]{0,6}$/.test(e.target.value)) onFieldChange('secondaryColor', e.target.value); }}
                        maxLength={7}
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>

            {/* Float Action Bar */}
            <div className={`fixed bottom-8 left-[calc(18rem+24rem)] right-16 flex justify-center transition-all duration-500 transform ${hasChanges ? 'translate-y-0 opacity-100' : 'translate-y-20 opacity-0 pointer-events-none'}`}>
              <div className="px-6 py-4 rounded-2xl border border-[var(--glass-border)] bg-[#1a1a24]/80 backdrop-blur-2xl shadow-2xl flex items-center gap-4 min-w-[400px]">
                <div className="flex-1">
                  <p className="text-sm font-bold text-white">{t('persona.unsaved')}</p>
                  <p className="text-[11px] text-white/50">Clique em salvar para aplicar todas as mudanças</p>
                </div>
                <div className="flex items-center gap-3">
                  <button
                    onClick={onCancel}
                    className="px-5 py-2.5 rounded-xl hover:bg-white/5 text-white/70 transition-all font-medium border border-transparent hover:border-white/10"
                  >
                    {t('common.cancel')}
                  </button>
                  <button
                    onClick={onSave}
                    className="px-6 py-2.5 rounded-xl bg-[var(--persona-primary)] text-white shadow-lg shadow-[var(--persona-primary)]/20 hover:scale-[1.02] active:scale-[0.98] transition-all font-bold flex items-center gap-2"
                  >
                    <Save size={18} />
                    {t('persona.save_changes')}
                  </button>
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="h-full flex flex-col items-center justify-center opacity-40">
            <Sparkles size={48} className="mb-4 text-[var(--persona-primary)] opacity-20" />
            <p className="text-sm font-medium" style={{ color: 'var(--text-tertiary)' }}>{t('persona.select')}</p>
          </div>
        )}
      </div>
    </div>
  );
}

interface PersonasTabProps {
  personas: any[];
  activePersona: string;
  selectedPersona: string | null;
  onSelectPersona: (name: string) => void;
  onSave: () => void;
  onCancel: () => void;
  onFieldChange: (field: keyof EditablePersona, value: string | File) => void;
  editedData: EditablePersona | null;
  hasChanges: boolean;
}

// ── Shared components Props ──────────────────────────────────
function SettingsSection({ title, description, icon, children }: { title: string; description: string; icon?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="bg-white/60 dark:bg-[rgba(255,255,255,0.02)] backdrop-blur-xl border rounded-[24px] p-7 transition-all duration-300" style={{ borderColor: 'var(--glass-border)', boxShadow: '0 8px 32px -8px color-mix(in srgb, var(--persona-shadow) 25%, rgba(0,0,0,0.08))' }}>
      <div className="mb-6 flex items-start gap-4">
        {icon && (
          <div className="p-2.5 rounded-2xl bg-[var(--surface-hover)] border border-[var(--glass-border)] flex-shrink-0 shadow-sm">
            {icon}
          </div>
        )}
        <div className="flex-1">
          <h3 className="text-base font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>{title}</h3>
          <p className="text-[13px] mt-1.5 leading-relaxed" style={{ color: 'var(--text-tertiary)' }}>{description}</p>
        </div>
      </div>
      <div className="space-y-5">{children}</div>
    </section>
  );
}

function KeyInput({ label, value, onChange, placeholder, hint }: { label: string; value: string; onChange: (v: string) => void; placeholder?: string; hint?: string }) {
  const [visible, setVisible] = useState(false);
  
  const handlePaste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      if (text) onChange(text);
    } catch (e) {
      console.error('Failed to paste', e);
    }
  };

  const isConfigured = value && value.trim().length > 0;

  return (
    <div>
      <div className="flex items-center justify-between">
        <label className="settings-label mb-0">{label}</label>
        {isConfigured && (
          <span className="text-[10px] flex items-center gap-1 text-emerald-400 font-medium">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
            Configured
          </span>
        )}
      </div>
      <div className="flex gap-1 mt-1">
        <input type={visible ? 'text' : 'password'} className="settings-input flex-1 font-mono text-xs" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} autoComplete="off" />
        
        {/* Toggle */}
        <button onClick={() => setVisible(!visible)} className="settings-key-toggle" title={visible ? 'Hide' : 'Show'} type="button">
          {visible ? (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
              <line x1="1" y1="1" x2="23" y2="23" />
            </svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
              <circle cx="12" cy="12" r="3" />
            </svg>
          )}
        </button>

        {/* Paste */}
        <button onClick={handlePaste} className="settings-key-toggle text-[var(--persona-primary)]" title="Paste clipboard" type="button">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"></path><rect x="8" y="2" width="8" height="4" rx="1" ry="1"></rect></svg>
        </button>

        {/* Copy */}
        {isConfigured && (
          <button 
            onClick={() => {
              if (window.ahri?.agent?.writeClipboard) {
                window.ahri.agent.writeClipboard(value);
              } else {
                navigator.clipboard.writeText(value);
              }
            }} 
            className="settings-key-toggle text-[var(--persona-primary)]" 
            title="Copy to clipboard" 
            type="button"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
            </svg>
          </button>
        )}

        {/* Clear */}
        {isConfigured && (
          <button onClick={() => onChange('')} className="settings-key-toggle text-red-400 hover:text-red-300" title="Clear key" type="button">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>
        )}
      </div>
      {hint && <p className="text-[10px] mt-1" style={{ color: 'var(--text-tertiary)' }}>{hint}</p>}
    </div>
  );
}

function SettingsToggle({ label, description, checked, onChange }: { label: string; description: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="settings-toggle-row">
      <div className="flex-1">
        <p className="text-sm" style={{ color: 'var(--text-primary)' }}>{label}</p>
        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>{description}</p>
      </div>
      <button type="button" onClick={() => onChange(!checked)} className={`settings-toggle-switch ${checked ? 'active' : ''}`}>
        <div className="settings-toggle-knob" />
      </button>
    </label>
  );
}

// ── Model Tester Section ──────────────────────────────────────
function ModelTesterSection({ apiKey }: { apiKey: string }) {
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [models, setModels] = useState<any[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [copiedModel, setCopiedModel] = useState<string | null>(null);
  const t = useT();
  const locale = useI18nStore((s) => s.locale);

  const handleCheck = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.checkGoogleModels(apiKey);
      setModels(res.models);
      if (res.models.length === 0) {
        setError(locale === 'pt' ? 'Nenhum modelo compatível encontrado.' : 'No compatible models found.');
      }
    } catch (e: any) {
      console.error('Failed to check models:', e);
      setError(e.message || 'Error connecting to Google');
    } finally {
      setLoading(false);
    }
  };

  const copyToClipboard = (text: string) => {
    if (window.ahri?.agent?.writeClipboard) {
      window.ahri.agent.writeClipboard(text);
    } else {
      navigator.clipboard.writeText(text);
    }
    setCopiedModel(text);
    setTimeout(() => setCopiedModel(null), 2000);
  };

  return (
    <div className="mt-8 pt-6 border-t" style={{ borderColor: 'var(--glass-border)' }}>
      <button 
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-between w-full group"
      >
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center bg-[var(--persona-primary)]/10 text-[var(--persona-primary)]">
            <FlaskConical size={16} />
          </div>
          <div className="text-left">
            <h4 className="text-xs font-bold uppercase tracking-wider" style={{ color: 'var(--text-primary)' }}>
              {t('api.tester.title' as any)}
            </h4>
            <p className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
              {t('api.tester.desc' as any)}
            </p>
          </div>
        </div>
        <div 
          className={`w-6 h-6 rounded-full flex items-center justify-center transition-all bg-[var(--glass-bg)] border border-[var(--glass-border)] ${isOpen ? 'rotate-180' : ''}`}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </div>
      </button>

      {isOpen && (
        <div className="mt-6 space-y-4 animate-fade-in">
          <div className="flex items-center justify-between p-4 rounded-2xl bg-[var(--glass-bg)] border border-[var(--glass-border)]">
            <div className="flex-1">
              <p className="text-[11px] leading-relaxed max-w-sm" style={{ color: 'var(--text-tertiary)' }}>
                {t('api.tester.desc' as any)}
              </p>
            </div>
            <button
              onClick={handleCheck}
              disabled={loading || !apiKey}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-bold transition-all shadow-lg ${
                loading 
                  ? 'bg-amber-500/20 text-amber-500 cursor-not-allowed opacity-50' 
                  : 'bg-[var(--persona-primary)] text-white hover:opacity-90 active:scale-95 shadow-[var(--persona-shadow)]'
              }`}
            >
              {loading ? (
                <>
                  <Activity size={14} />
                  {t('api.tester.checking' as any)}
                </>
              ) : (
                <>
                  <CheckCircle size={14} />
                  {t('api.tester.check' as any)}
                </>
              )}
            </button>
          </div>

          {error && (
            <div className="p-3 rounded-xl bg-red-500/10 border border-red-500/20 text-red-400 text-[11px] flex items-center gap-2">
              <Activity size={14} />
              {error}
            </div>
          )}

          {models.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 max-h-[320px] overflow-y-auto pr-2 custom-scrollbar p-1">
              {models.map((m) => (
                <button 
                  key={m.name}
                  onClick={() => copyToClipboard(m.name.replace('models/', ''))}
                  className="group relative flex flex-row items-center justify-between p-3 rounded-xl border border-[var(--glass-border)] bg-[var(--glass-bg)] hover:bg-[var(--persona-primary)]/5 hover:border-[var(--persona-primary)]/40 transition-all text-left overflow-hidden gap-3"
                  title={t('api.tester.copy_hint' as any)}
                >
                  <div className="flex flex-col min-w-0">
                    <span className="text-[11px] font-bold truncate" style={{ color: 'var(--text-primary)' }}>
                      {m.display_name}
                    </span>
                    <code className="text-[9px] font-mono mt-0.5 truncate" style={{ color: 'var(--text-tertiary)' }}>
                      {m.name.replace('models/', '')}
                    </code>
                  </div>

                  <div className={`flex-shrink-0 transition-all p-1.5 rounded-lg shadow-sm ${
                    copiedModel === m.name.replace('models/', '')
                      ? 'bg-emerald-500 text-white' 
                      : 'opacity-0 group-hover:opacity-100 bg-[var(--persona-primary)] text-white'
                  }`}>
                    {copiedModel === m.name.replace('models/', '') ? (
                      <CheckCircle size={12} />
                    ) : (
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                      </svg>
                    )}
                  </div>
                  
                  {/* Subtle background glow on hover */}
                  <div className="absolute inset-0 bg-gradient-to-r from-[var(--persona-primary)]/5 to-transparent opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
