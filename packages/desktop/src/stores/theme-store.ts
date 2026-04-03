import { create } from 'zustand';

export type AppTheme = 'dark' | 'light';

interface ThemeState {
    theme: AppTheme;
    setTheme: (theme: AppTheme) => void;
    toggleTheme: () => void;
}

const STORAGE_KEY = 'ahri_theme';

function getStoredTheme(): AppTheme {
    try {
        const stored = localStorage.getItem(STORAGE_KEY);
        if (stored === 'light' || stored === 'dark') return stored;
    } catch {
        // localStorage not available
    }
    return 'light'; // default
}

function applyTheme(theme: AppTheme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem(STORAGE_KEY, theme);
    
    // Notify Electron main process to update native titlebar overlay
    if (typeof window !== 'undefined' && (window as any).ahri?.window?.setTheme) {
        (window as any).ahri.window.setTheme(theme);
    }
}

export const useThemeStore = create<ThemeState>((set) => {
    // Apply stored theme on init
    const initial = getStoredTheme();
    // Defer DOM manipulation to avoid SSR issues
    if (typeof document !== 'undefined') {
        applyTheme(initial);
    }

    return {
        theme: initial,

        setTheme: (theme) => {
            applyTheme(theme);
            set({ theme });
        },

        toggleTheme: () => {
            set((state) => {
                const next = state.theme === 'dark' ? 'light' : 'dark';
                applyTheme(next);
                return { theme: next };
            });
        },
    };
});
