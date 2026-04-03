/**
 * Tipos para o sistema de memória.
 */

export interface UserProfile {
  // Manual
  name: string;
  occupation: string;
  custom_instructions: string;

  // Auto Narrative Context
  work_context: string;
  personal_context: string;
  top_of_mind: string;
  brief_history: string;

  // Legacy (To be deprecated)
  archetype: string;
  learning_style: string;
  attributes: {
    languages?: Record<string, string>;
    tech_stack?: string[];
    interests?: string[];
    [key: string]: unknown;
  };
  preferences: {
    foods?: string[];
    music?: string[];
    dislikes?: string[];
    [key: string]: unknown;
  };
  knowledge_tracker: {
    vocabulary_recent?: string[];
    concepts_mastered?: string[];
    [key: string]: unknown;
  };
  active_quests: Record<string, LearningQuest>;
  session_log: string[];
}

export interface LearningQuest {
  status: 'In Progress' | 'Completed' | 'Paused';
  current_stage: string;
  progress: Record<string, string>;
}

export interface SpotifyContext {
  is_playing: boolean;
  track_name: string;
  artist_name: string;
  album_name: string;
  genres: string[];
  suggested_persona: string;
}

export interface SyncState {
  active_persona: string;
  active_session_id: number | null;
  user_profile: UserProfile;
  recent_messages: import('./chat.js').ChatMessage[];
  spotify_context: SpotifyContext | null;
}

// =============================================================================
// Memory Management (Settings UI)
// =============================================================================

export interface AutoProfile {
  // Narrative Context
  work_context: string;
  personal_context: string;
  top_of_mind: string;
  brief_history: string;

  // Legacy
  attributes: Record<string, unknown>;
  knowledge_tracker: {
    vocabulary_recent?: string[];
    concepts_mastered?: string[];
    [key: string]: unknown;
  };
  active_quests: Record<string, LearningQuest>;
  session_log: string[];
}

export interface AutoProfilePatch {
  remove_attribute_keys?: string[];
  update_attributes?: Record<string, any>;
  remove_vocabulary_indices?: number[];
  remove_concept_indices?: number[];
  remove_quest_keys?: string[];
  remove_session_log_indices?: number[];
}

export interface RagFileInfo {
  filename: string;
  source_type: 'static_lore' | 'dynamic_knowledge';
  size_bytes: number;
  chunk_count: number;
  last_modified: number;
}

export interface RagStats {
  total_chunks: number;
  by_type: Record<string, number>;
  persona: string;
}

export interface RagMemoryItem {
  id: string;
  content: string;
  type: string;
  filename: string;
  source: string;
  distance?: number;
}

export interface SocialGraphPlatform {
  platform: string;
  data: Record<string, unknown>;
  updated_at?: string;
}

export interface EpisodicMemoryEntry {
  id: number;
  persona_name: string;
  date: string;
  topics: string[];
  emotional_tone: string;
  summary: string;
  importance: number;
  outcomes: string[];
}

export interface ForgetResponse {
  status: string;
  topic: string;
  deleted_chunks: number;
  deleted_files: string[];
  removed_profile_entries: string[];
}

// Persona Memory (per-persona quests, session logs, buffer)
export interface PersonaMemoryData {
  persona_name: string;
  active_quests: Record<string, unknown>;
  session_log: string[];
  session_log_detailed: Array<Record<string, unknown>>;
  last_session_buffer: string[];
}

export interface PersonaMemoryPatch {
  remove_quest_keys?: string[];
  remove_session_log_indices?: number[];
  remove_session_log_detailed_indices?: number[];
  clear_buffer?: boolean;
}

// =============================================================================
// Dual-Layer Memory Architecture (v3.2.0)
// =============================================================================

/** Layer 1: Explicit user-controlled preferences. AI never writes here. */
export interface UserPreferences {
  display_name: string;
  pronouns: string;
  occupation: string;
  location: string;
  custom_instructions: string;
  topics_to_avoid: string;
  persona_style: string;
}

export type MemoryTier =
  | 'immediate_context'
  | 'top_of_mind'
  | 'recent_history'
  | 'work_context'
  | 'personal_context'
  | 'long_term_background';

/** Layer 2: A single AI-managed memory fact in a hierarchical tier. */
export interface SemanticMemoryItem {
  id: number;
  tier: MemoryTier;
  content: string;
  source_session_id: number | null;
  created_at: string;
  last_reinforced: string;
  decay_date: string | null;
  is_flagged: boolean;
  conflict_note: string;
  importance: number;
  tags: string[];
}

export interface SemanticTiersResponse {
  immediate_context: SemanticMemoryItem[];
  top_of_mind: SemanticMemoryItem[];
  recent_history: SemanticMemoryItem[];
  work_context: SemanticMemoryItem[];
  personal_context: SemanticMemoryItem[];
  long_term_background: SemanticMemoryItem[];
}

export interface AddSemanticFactRequest {
  tier: MemoryTier;
  content: string;
  importance?: number;
  tags?: string[];
  source_session_id?: number;
}

export interface MigrateLegacyResponse {
  status: string;
  migrated_facts: number;
}
