"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
const electron_1 = require("electron");
/**
 * Preload script - ponte segura entre o processo main (Node.js) e o renderer (React).
 * Expõe APIs específicas via contextBridge ao invés de dar acesso total ao Node.
 */
electron_1.contextBridge.exposeInMainWorld('ahri', {
    // System
    platform: process.platform,
    isElectron: true,
    // Agent IPC (para capabilities que precisam de acesso ao sistema)
    agent: {
        openFile: (path) => electron_1.ipcRenderer.invoke('agent:open-file', path),
        readFile: (path) => electron_1.ipcRenderer.invoke('agent:read-file', path),
        writeFile: (path, content) => electron_1.ipcRenderer.invoke('agent:write-file', { path, content }),
        deleteFile: (path) => electron_1.ipcRenderer.invoke('agent:delete-file', path),
        listDir: (path) => electron_1.ipcRenderer.invoke('agent:list-dir', path),
        openUrl: (url) => electron_1.ipcRenderer.invoke('agent:open-url', url),
        getSystemInfo: () => electron_1.ipcRenderer.invoke('agent:system-info'),
        readClipboard: () => electron_1.ipcRenderer.invoke('agent:clipboard-read'),
        writeClipboard: (text) => electron_1.ipcRenderer.invoke('agent:clipboard-write', text),
        getPaths: () => electron_1.ipcRenderer.invoke('agent:get-paths'),
        // Agent Mode v2 — directory, terminal, editor
        selectDirectory: () => electron_1.ipcRenderer.invoke('agent:select-directory'),
        getRecentDirs: () => electron_1.ipcRenderer.invoke('agent:get-recent-dirs'),
        addRecentDir: (dir) => electron_1.ipcRenderer.invoke('agent:add-recent-dir', dir),
        openTerminal: (dir) => electron_1.ipcRenderer.invoke('agent:open-terminal', dir),
        openEditor: (dir) => electron_1.ipcRenderer.invoke('agent:open-editor', dir),
    },
    // Window management
    window: {
        minimize: () => electron_1.ipcRenderer.invoke('window:minimize'),
        maximize: () => electron_1.ipcRenderer.invoke('window:maximize'),
        close: () => electron_1.ipcRenderer.invoke('window:close'),
        setTheme: (theme) => electron_1.ipcRenderer.invoke('window:set-theme', theme),
    },
    // Auto-Persona daemon
    autoPersona: {
        start: () => electron_1.ipcRenderer.invoke('auto-persona:start'),
        stop: () => electron_1.ipcRenderer.invoke('auto-persona:stop'),
        status: () => electron_1.ipcRenderer.invoke('auto-persona:status'),
        onPersonaSwitched: (callback) => {
            electron_1.ipcRenderer.on('persona:auto-switched', (_event, persona) => callback(persona));
        },
    },
    // Settings (hardware acceleration, GPU info)
    settings: {
        getHwAccel: () => electron_1.ipcRenderer.invoke('settings:get-hw-accel'),
        setHwAccel: (enabled) => electron_1.ipcRenderer.invoke('settings:set-hw-accel', enabled),
        restartApp: () => electron_1.ipcRenderer.invoke('settings:restart-app'),
        getGpuInfo: () => electron_1.ipcRenderer.invoke('settings:get-gpu-info'),
    },
});
