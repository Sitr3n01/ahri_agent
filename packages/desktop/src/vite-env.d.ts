/// <reference types="vite/client" />

interface AhriAPI {
  platform: string;
  isElectron: boolean;
  agent: {
    openFile: (path: string) => Promise<void>;
    readFile: (path: string) => Promise<string>;
    writeFile: (path: string, content: string) => Promise<{ success: true }>;
    listDir: (path: string) => Promise<string[]>;
    openUrl: (url: string) => Promise<void>;
    getSystemInfo: () => Promise<Record<string, unknown>>;
    readClipboard: () => Promise<string>;
    writeClipboard: (text: string) => Promise<void>;
    // Agent Mode v2
    selectDirectory: () => Promise<string | null>;
    getRecentDirs: () => Promise<string[]>;
    addRecentDir: (dir: string) => Promise<string[]>;
    openTerminal: (dir: string) => Promise<{ success: boolean; error?: string }>;
    openEditor: (dir: string) => Promise<{ success: boolean; error?: string }>;
    getPaths: () => Promise<{ root: string; data: string; personas: string }>;
  };
  window: {
    minimize: () => Promise<void>;
    maximize: () => Promise<void>;
    close: () => Promise<void>;
    setTheme: (theme: string) => Promise<void>;
  };
  autoPersona: {
    start: () => Promise<{ success: boolean }>;
    stop: () => Promise<{ success: boolean }>;
    status: () => Promise<{ enabled: boolean }>;
    onPersonaSwitched: (callback: (persona: string) => void) => void;
  };
  settings: {
    getHwAccel: () => Promise<boolean>;
    setHwAccel: (enabled: boolean) => Promise<{ requiresRestart: boolean }>;
    restartApp: () => Promise<void>;
    getGpuInfo: () => Promise<{
      featureStatus: Record<string, string>;
      gpuInfo: unknown;
      hardwareAcceleration: boolean;
    }>;
  };
}

declare global {
  interface Window {
    ahri?: AhriAPI;
  }
}
