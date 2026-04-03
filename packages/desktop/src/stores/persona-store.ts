import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { PersonaSummary, SpotifyContext } from '@ahri/shared';
import { getPersonaTheme, mergePersonaTheme, type PersonaTheme } from '@ahri/shared';
import { api } from '@/api/client';

interface PersonaState {
  activePersona: string;
  personas: PersonaSummary[];
  isLoading: boolean;
  error: string | null;
  backgroundOpacity: number; // 0-100 (percentage)
  spotifyContext: SpotifyContext | null;
  isSyncingSpotify: boolean;

  setActivePersona: (name: string) => void;
  fetchPersonas: (retryCount?: number) => Promise<void>;
  activatePersona: (name: string) => Promise<void>;
  getTheme: () => PersonaTheme;
  getMergedTheme: (name: string) => PersonaTheme;
  setBackgroundOpacity: (opacity: number) => void;
  fetchSpotifyContext: () => Promise<void>;
  syncPersonaByMusic: () => Promise<string | null>;
}

export const usePersonaStore = create<PersonaState>()(
  persist(
    (set, get) => ({
      activePersona: 'ahri',
      personas: [],
      isLoading: false,
      error: null,
      backgroundOpacity: 40, // Default 40%
      spotifyContext: null,
      isSyncingSpotify: false,

      setActivePersona: (name) => set({ activePersona: name }),

      fetchPersonas: async (retryCount = 0) => {
        set({ isLoading: true, error: null });
        try {
          const data = await api.listPersonas();
          set({
            personas: data.personas,
            activePersona: data.active,
            isLoading: false,
            error: null,
          });
        } catch (e: any) {
          const message = e?.message || 'Falha ao carregar personas';
          console.error(`Failed to fetch personas (attempt ${retryCount + 1}):`, e);

          if (retryCount < 2) {
            // Auto-retry after 2s, max 2 retries
            setTimeout(() => {
              get().fetchPersonas(retryCount + 1);
            }, 2000);
          } else {
            set({ isLoading: false, error: message });
          }
        }
      },

      activatePersona: async (name) => {
        const previousPersona = get().activePersona;
        // Optimistic update
        set({ activePersona: name });
        try {
          const result = await api.activatePersona(name);
          set({ activePersona: result.active });
        } catch (e) {
          console.error('Failed to activate persona:', e);
          // Rollback on failure
          set({ activePersona: previousPersona });
        }
      },

      getTheme: () => {
        return get().getMergedTheme(get().activePersona);
      },

      getMergedTheme: (name: string) => {
        if (!name) return getPersonaTheme('');
        const persona = get().personas.find(p => p.name && p.name.toLowerCase() === name.toLowerCase());
        const staticTheme = getPersonaTheme(name);
        return mergePersonaTheme(staticTheme, persona?.theme);
      },

      setBackgroundOpacity: (opacity) => set({ backgroundOpacity: opacity }),

      fetchSpotifyContext: async () => {
        try {
          const ctx = await api.getSpotifyContext();
          set({ spotifyContext: ctx });
        } catch (e) {
          console.error('Failed to fetch Spotify context:', e);
        }
      },

      syncPersonaByMusic: async () => {
        set({ isSyncingSpotify: true });
        try {
          const result = await api.syncPersonaByMusic();
          if (result.switched) {
            set({ activePersona: result.persona, isSyncingSpotify: false });
            return result.persona;
          }
          set({ isSyncingSpotify: false });
          return null;
        } catch (e) {
          console.error('Failed to sync persona by music:', e);
          set({ isSyncingSpotify: false });
          return null;
        }
      },
    }),
    {
      name: 'persona-preferences',
      partialize: (state) => ({ backgroundOpacity: state.backgroundOpacity }),
    }
  )
);
