/**
 * Ahri API Client - HTTP + WebSocket para comunicação com o backend.
 * Usado pelo desktop (Electron) e web (mobile PWA).
 */

import type { TokenResponse, HealthResponse } from '../types/api.js';
import type { PersonaListResponse, PersonaDetail } from '../types/persona.js';
import type { ChatRequest, ChatResponse, SessionSummary, SessionDetail } from '../types/chat.js';
import type {
  UserProfile, SpotifyContext, AutoProfile, AutoProfilePatch,
  RagFileInfo, RagStats, RagMemoryItem, SocialGraphPlatform,
  EpisodicMemoryEntry, ForgetResponse,
  PersonaMemoryData, PersonaMemoryPatch,
  // v3.2.0 dual-layer memory
  UserPreferences, SemanticMemoryItem, SemanticTiersResponse,
  MemoryTier, AddSemanticFactRequest, MigrateLegacyResponse,
} from '../types/memory.js';
import type { AvailableModel, GoogleModelCheckResponse } from '../types/llm.js';

export interface AhriClientConfig {
  baseUrl: string;
  onTokenExpired?: () => void;
}

export class AhriApiClient {
  private baseUrl: string;
  private accessToken: string = '';
  private refreshToken: string = '';
  private onTokenExpired?: () => void;

  constructor(config: AhriClientConfig) {
    this.baseUrl = config.baseUrl.replace(/\/$/, '');
    this.onTokenExpired = config.onTokenExpired;
  }

  // =========================================================================
  // Token Management
  // =========================================================================

  setTokens(access: string | null, refresh: string | null) {
    this.accessToken = access || '';
    this.refreshToken = refresh || '';
  }

  getAccessToken(): string {
    return this.accessToken;
  }

  isAuthenticated(): boolean {
    return !!this.accessToken;
  }

  async refreshTokenManual(refreshToken: string): Promise<TokenResponse> {
    const res = await fetch(`${this.baseUrl}/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!res.ok) {
      throw new ApiError(res.status, await res.text());
    }

    const data = (await res.json()) as TokenResponse;
    this.accessToken = data.access_token;
    this.refreshToken = data.refresh_token;
    return data;
  }

  // =========================================================================
  // HTTP Helpers
  // =========================================================================

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
    requireAuth = true,
  ): Promise<T> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    };

    if (requireAuth && this.accessToken) {
      headers['Authorization'] = `Bearer ${this.accessToken}`;
    }

    const res = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });

    if (res.status === 401 && requireAuth) {
      // Tenta refresh
      const refreshed = await this.tryRefresh();
      if (refreshed) {
        headers['Authorization'] = `Bearer ${this.accessToken}`;
        const retry = await fetch(`${this.baseUrl}${path}`, {
          method,
          headers,
          body: body ? JSON.stringify(body) : undefined,
        });
        if (!retry.ok) throw new ApiError(retry.status, await retry.text());
        return retry.json() as T;
      }
      this.onTokenExpired?.();
      throw new ApiError(401, 'Authentication expired');
    }

    if (!res.ok) {
      const text = await res.text();
      throw new ApiError(res.status, text);
    }

    return res.json() as T;
  }

  private async tryRefresh(): Promise<boolean> {
    if (!this.refreshToken) return false;

    try {
      const res = await fetch(`${this.baseUrl}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: this.refreshToken }),
      });

      if (!res.ok) return false;

      const data = (await res.json()) as TokenResponse;
      this.accessToken = data.access_token;
      this.refreshToken = data.refresh_token;
      return true;
    } catch {
      return false;
    }
  }

  // =========================================================================
  // Auth
  // =========================================================================

  async login(password: string): Promise<TokenResponse> {
    const data = await this.request<TokenResponse>('POST', '/auth/login', { password }, false);
    this.accessToken = data.access_token;
    this.refreshToken = data.refresh_token;
    return data;
  }

  // =========================================================================
  // Password Reset
  // =========================================================================

  async resetPassword(currentPassword: string, newPassword: string): Promise<TokenResponse> {
    const data = await this.request<TokenResponse>('POST', '/auth/reset-password', {
      current_password: currentPassword,
      new_password: newPassword,
    });
    this.accessToken = data.access_token;
    this.refreshToken = data.refresh_token;
    return data;
  }

  async forceResetPassword(newPassword: string): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>(
      'POST', '/auth/force-reset',
      { new_password: newPassword },
      false, // No auth required
    );
  }

  // =========================================================================
  // Health
  // =========================================================================

  async health(): Promise<HealthResponse> {
    return this.request<HealthResponse>('GET', '/health', undefined, false);
  }

  // =========================================================================
  // Personas
  // =========================================================================

  async listPersonas(): Promise<PersonaListResponse> {
    return this.request<PersonaListResponse>('GET', '/personas');
  }

  async getPersona(name: string): Promise<PersonaDetail> {
    return this.request<PersonaDetail>('GET', `/personas/${encodeURIComponent(name)}`);
  }

  async activatePersona(name: string): Promise<{ active: string }> {
    return this.request<{ active: string }>('POST', `/personas/${encodeURIComponent(name)}/activate`);
  }

  async updatePersona(name: string, data: Record<string, any>): Promise<PersonaDetail> {
    return this.request<PersonaDetail>('PUT', `/personas/${encodeURIComponent(name)}`, data);
  }

  // =========================================================================
  // Chat
  // =========================================================================

  async sendMessage(req: ChatRequest): Promise<ChatResponse> {
    return this.request<ChatResponse>('POST', '/chat', req);
  }

  // =========================================================================
  // Sessions
  // =========================================================================

  async listSessions(persona?: string): Promise<SessionSummary[]> {
    const query = persona ? `?persona=${encodeURIComponent(persona)}` : '';
    return this.request<SessionSummary[]>('GET', `/sessions${query}`);
  }

  async createSession(title?: string): Promise<SessionSummary> {
    return this.request<SessionSummary>('POST', '/sessions', { title: title ?? '' });
  }

  async getSession(id: number): Promise<SessionDetail> {
    return this.request<SessionDetail>('GET', `/sessions/${id}`);
  }

  async renameSession(id: number, title: string): Promise<void> {
    await this.request<unknown>('PUT', `/sessions/${id}`, { title });
  }

  async deleteSession(id: number): Promise<void> {
    await this.request<unknown>('DELETE', `/sessions/${id}`);
  }

  // =========================================================================
  // Memory
  // =========================================================================

  async getProfile(): Promise<UserProfile> {
    return this.request<UserProfile>('GET', '/memory/profile');
  }

  async saveProfile(profile: UserProfile): Promise<{ status: string; profile: UserProfile }> {
    return this.request<{ status: string; profile: UserProfile }>('POST', '/memory/profile', profile);
  }

  async synthesizeProfile(): Promise<{ status: string; message: string }> {
    return this.request<{ status: string; message: string }>('POST', '/memory/profile/synthesize');
  }

  async saveMemory(title: string, content: string): Promise<void> {
    await this.request<unknown>('POST', '/memory/save', { title, content });
  }

  async learnFact(topic: string, content: string): Promise<void> {
    await this.request<unknown>('POST', '/memory/learn', { topic, content });
  }

  async forgetFact(topic: string): Promise<ForgetResponse> {
    return this.request<ForgetResponse>('POST', '/memory/forget', { topic });
  }

  async listMemories(sourceType?: string): Promise<{ memories: Array<{ id: string; content: string; type: string; filename: string; source: string }>; total: number; persona: string }> {
    const query = sourceType ? `?source_type=${encodeURIComponent(sourceType)}` : '';
    return this.request('GET', `/memory/list${query}`);
  }

  async getMemory(id: string): Promise<{ id: string; content: string; type: string; filename: string; source: string }> {
    return this.request('GET', `/memory/${encodeURIComponent(id)}`);
  }

  async updateMemory(id: string, content: string): Promise<{ status: string; id: string }> {
    return this.request('PUT', `/memory/${encodeURIComponent(id)}`, { content });
  }

  async deleteMemory(id: string): Promise<{ status: string; id: string }> {
    return this.request('DELETE', `/memory/${encodeURIComponent(id)}`);
  }

  // =========================================================================
  // Memory Management (Settings UI)
  // =========================================================================

  // --- Auto-Profile ---
  async getAutoProfile(): Promise<AutoProfile> {
    return this.request<AutoProfile>('GET', '/memory/auto-profile');
  }

  async patchAutoProfile(patch: AutoProfilePatch): Promise<{ status: string; removed: string[] }> {
    return this.request('PATCH', '/memory/auto-profile', patch);
  }

  async clearAutoProfileCategory(category: string): Promise<{ status: string }> {
    return this.request('POST', `/memory/auto-profile/clear/${encodeURIComponent(category)}`);
  }

  // --- RAG File Management ---
  async getRagFiles(persona?: string): Promise<RagFileInfo[]> {
    const query = persona ? `?persona=${encodeURIComponent(persona)}` : '';
    return this.request<RagFileInfo[]>('GET', `/memory/rag/files${query}`);
  }

  async getRagFilePath(filename: string, sourceType = 'dynamic_knowledge', persona?: string): Promise<{ path: string }> {
    const query = new URLSearchParams({ source_type: sourceType });
    if (persona) query.set('persona', persona);
    return this.request<{ path: string }>('GET', `/memory/rag/files/${encodeURIComponent(filename)}/path?${query.toString()}`);
  }

  async deleteRagFile(filename: string, sourceType = 'dynamic_knowledge'): Promise<{ status: string; deleted_chunks: number }> {
    return this.request('DELETE', `/memory/rag/files/${encodeURIComponent(filename)}?source_type=${encodeURIComponent(sourceType)}`);
  }

  async reindexRag(persona?: string): Promise<{ status: string; chunks_indexed: number }> {
    const query = persona ? `?persona=${encodeURIComponent(persona)}` : '';
    return this.request('POST', `/memory/rag/reindex${query}`);
  }

  async getRagStats(persona?: string): Promise<RagStats> {
    const query = persona ? `?persona=${encodeURIComponent(persona)}` : '';
    return this.request<RagStats>('GET', `/memory/rag/stats${query}`);
  }

  async searchRagMemories(queryText: string, sourceType?: string, limit = 20): Promise<{ memories: RagMemoryItem[]; total: number; persona: string }> {
    return this.request('POST', '/memory/rag/search', { query: queryText, source_type: sourceType, limit });
  }

  // --- Social Graph ---
  async getSocialGraph(): Promise<SocialGraphPlatform[]> {
    return this.request<SocialGraphPlatform[]>('GET', '/memory/social-graph');
  }

  async upsertSocialGraphPlatform(platform: string, data: Record<string, unknown>): Promise<{ status: string }> {
    return this.request('PUT', `/memory/social-graph/${encodeURIComponent(platform)}`, data);
  }

  async deleteSocialGraphPlatform(platform: string): Promise<{ status: string }> {
    return this.request('DELETE', `/memory/social-graph/${encodeURIComponent(platform)}`);
  }

  async importSocialGraph(platforms: Record<string, Record<string, unknown>>): Promise<{ status: string; imported: number }> {
    return this.request('POST', '/memory/social-graph/import', { platforms });
  }

  // --- Episodic Memory ---
  async getEpisodes(params?: { persona?: string; min_importance?: number; min_date?: string; max_date?: string; limit?: number; offset?: number }): Promise<EpisodicMemoryEntry[]> {
    const searchParams = new URLSearchParams();
    if (params?.persona) searchParams.set('persona', params.persona);
    if (params?.min_importance) searchParams.set('min_importance', String(params.min_importance));
    if (params?.min_date) searchParams.set('min_date', params.min_date);
    if (params?.max_date) searchParams.set('max_date', params.max_date);
    if (params?.limit) searchParams.set('limit', String(params.limit));
    if (params?.offset) searchParams.set('offset', String(params.offset));
    const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
    return this.request<EpisodicMemoryEntry[]>('GET', `/memory/episodes${query}`);
  }

  async deleteEpisode(id: number): Promise<{ status: string }> {
    return this.request('DELETE', `/memory/episodes/${id}`);
  }

  async bulkDeleteEpisodes(ids: number[]): Promise<{ status: string; deleted: number }> {
    return this.request('POST', '/memory/episodes/bulk-delete', { ids });
  }

  // Persona Memory (per-persona quests, session logs, buffer)
  async getPersonaMemory(persona?: string): Promise<PersonaMemoryData> {
    const query = persona ? `?persona=${encodeURIComponent(persona)}` : '';
    return this.request<PersonaMemoryData>('GET', `/memory/persona-memory${query}`);
  }

  async patchPersonaMemory(patch: PersonaMemoryPatch, persona?: string): Promise<{ status: string }> {
    const query = persona ? `?persona=${encodeURIComponent(persona)}` : '';
    return this.request('PATCH', `/memory/persona-memory${query}`, patch);
  }

  async clearPersonaBuffer(persona?: string): Promise<{ status: string }> {
    const query = persona ? `?persona=${encodeURIComponent(persona)}` : '';
    return this.request('DELETE', `/memory/persona-memory/buffer${query}`);
  }

  // =========================================================================
  // Search
  // =========================================================================

  async search(query: string, maxResults = 5): Promise<{ results: Array<{ title: string; link: string; snippet: string }>; remaining_quota: number }> {
    return this.request('POST', '/search', { query, max_results: maxResults });
  }

  // =========================================================================
  // Spotify
  // =========================================================================

  async getSpotifyContext(): Promise<SpotifyContext> {
    return this.request<SpotifyContext>('GET', '/spotify/context');
  }

  async syncPersonaByMusic(): Promise<{ switched: boolean; persona: string }> {
    return this.request('POST', '/spotify/sync-persona');
  }

  // =========================================================================
  // Settings
  // =========================================================================

  async getSettings(): Promise<any> {
    return this.request<any>('GET', '/settings');
  }

  async updateSettings(settings: Record<string, any>): Promise<{ status: string }> {
    return this.request<{ status: string }>('POST', '/settings', { settings });
  }

  // =========================================================================
  // Models
  // =========================================================================

  async getAvailableModels(): Promise<AvailableModel[]> {
    return this.request<AvailableModel[]>('GET', '/settings/models/available');
  }

  async checkGoogleModels(apiKey?: string): Promise<GoogleModelCheckResponse> {
    return this.request<GoogleModelCheckResponse>('POST', '/settings/check-google-models', { api_key: apiKey });
  }

  // =========================================================================
  // WebSocket
  // =========================================================================

  createChatWebSocket(): WebSocket {
    const wsUrl = this.baseUrl.replace(/^http/, 'ws');
    return new WebSocket(`${wsUrl}/chat/ws`);
  }

  // =========================================================================
  // Layer 1 — User Preferences (v3.2.0)
  // =========================================================================

  async getPreferences(): Promise<UserPreferences> {
    return this.request<UserPreferences>('GET', '/memory/preferences');
  }

  async updatePreferences(data: Partial<UserPreferences>): Promise<UserPreferences> {
    return this.request<UserPreferences>('PUT', '/memory/preferences', data);
  }

  // =========================================================================
  // Layer 2 — Semantic Memory Tiers (v3.2.0)
  // =========================================================================

  async getSemanticTiers(): Promise<SemanticTiersResponse> {
    return this.request<SemanticTiersResponse>('GET', '/memory/semantic-tiers');
  }

  async getSemanticTier(tier: MemoryTier): Promise<SemanticMemoryItem[]> {
    return this.request<SemanticMemoryItem[]>('GET', `/memory/semantic-tiers/${tier}`);
  }

  async addSemanticFact(data: AddSemanticFactRequest): Promise<SemanticMemoryItem> {
    return this.request<SemanticMemoryItem>('POST', '/memory/semantic-tiers', data);
  }

  async deleteSemanticFact(id: number): Promise<{ status: string; id: number }> {
    return this.request<{ status: string; id: number }>('DELETE', `/memory/semantic-tiers/${id}`);
  }

  async deleteSemanticTier(tier: MemoryTier): Promise<{ deleted: number }> {
    return this.request<{ deleted: number }>('DELETE', `/memory/semantic-tiers/tier/${tier}`);
  }

  async runDecayPass(): Promise<{ decayed: number }> {
    return this.request<{ decayed: number }>('POST', '/memory/semantic-tiers/decay');
  }

  async migrateLegacy(): Promise<MigrateLegacyResponse> {
    return this.request<MigrateLegacyResponse>('POST', '/memory/migrate-legacy');
  }
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

/**
 * Cria uma instância do client configurada para desenvolvimento local.
 */
export function createLocalClient(port = 8742): AhriApiClient {
  return new AhriApiClient({ baseUrl: `http://localhost:${port}` });
}
