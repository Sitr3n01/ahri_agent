/**
 * SettingsView - Settings and configuration for mobile
 */

import { useState } from 'react';
import { useAuthStore } from '@/stores/auth-store';
import { useChatStore } from '@/stores/chat-store';
import { useNavigate } from 'react-router-dom';
import { LogOut, Zap, Wifi, WifiOff, Download, Info } from 'lucide-react';

export function SettingsView() {
  const logout = useAuthStore((s) => s.logout);
  const model = useChatStore((s) => s.model);
  const setModel = useChatStore((s) => s.setModel);
  const navigate = useNavigate();

  const [isOnline, setIsOnline] = useState(navigator.onLine);

  // Listen to online/offline events
  useState(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  });

  const handleLogout = () => {
    if (confirm('Tem certeza que deseja sair?')) {
      logout();
      navigate('/login');
    }
  };

  const models: Array<{ value: any; label: string; description: string }> = [
    { value: 'PRO', label: 'Gemini Pro', description: 'Rápido e inteligente' },
    { value: 'GOOGLE', label: 'Flash Lite', description: 'Código e análise' },
    { value: 'DEEPSEEK', label: 'DeepSeek R1', description: 'Raciocínio profundo' },
    { value: 'LOCAL', label: 'Local (Ollama)', description: 'Offline' }
  ];

  return (
    <div className="h-full overflow-auto">
      {/* Header */}
      <div className="sticky top-0 bg-black/40 backdrop-blur-xl border-b border-white/10 px-4 py-4 z-10">
        <h1 className="text-2xl font-light text-white/90">Configurações</h1>
        <p className="text-white/50 text-sm mt-1">
          Ajustes e preferências
        </p>
      </div>

      <div className="p-4 space-y-6">
        {/* Connection Status */}
        <div className="glass-dark rounded-2xl p-4">
          <div className="flex items-center gap-3 mb-3">
            {isOnline ? (
              <Wifi size={20} className="text-green-400" />
            ) : (
              <WifiOff size={20} className="text-red-400" />
            )}
            <h2 className="text-white font-medium">Status de Conexão</h2>
          </div>
          <p className="text-white/60 text-sm">
            {isOnline ? 'Online - Sincronizado com o servidor' : 'Offline - Modo somente leitura'}
          </p>
        </div>

        {/* Model Selection */}
        <div className="glass-dark rounded-2xl p-4">
          <div className="flex items-center gap-3 mb-4">
            <Zap size={20} className="text-[var(--theme-primary)]" />
            <h2 className="text-white font-medium">Modelo de IA</h2>
          </div>

          <div className="space-y-2">
            {models.map((m) => (
              <button
                key={m.value}
                onClick={() => setModel(m.value)}
                className={`w-full text-left p-3 rounded-xl transition-all ${
                  model === m.value
                    ? 'bg-[var(--theme-primary)]/20 border-2 border-[var(--theme-primary)]'
                    : 'bg-black/20 border-2 border-transparent hover:bg-black/30'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-white font-medium">{m.label}</div>
                    <div className="text-white/50 text-sm">{m.description}</div>
                  </div>
                  {model === m.value && (
                    <div className="w-5 h-5 rounded-full bg-[var(--theme-primary)] flex items-center justify-center">
                      <div className="w-2 h-2 bg-white rounded-full" />
                    </div>
                  )}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* PWA Install */}
        <div className="glass-dark rounded-2xl p-4">
          <div className="flex items-center gap-3 mb-3">
            <Download size={20} className="text-blue-400" />
            <h2 className="text-white font-medium">Instalar App</h2>
          </div>
          <p className="text-white/60 text-sm mb-3">
            Adicione Ahri à sua tela inicial para acesso rápido
          </p>
          <button
            onClick={() => {
              // PWA install prompt (handled by browser)
              alert('Use o menu do navegador para adicionar à tela inicial');
            }}
            className="w-full py-2 bg-blue-500/20 hover:bg-blue-500/30 text-blue-400 rounded-xl font-medium transition-all active:scale-95"
          >
            Adicionar à Tela Inicial
          </button>
        </div>

        {/* About */}
        <div className="glass-dark rounded-2xl p-4">
          <div className="flex items-center gap-3 mb-3">
            <Info size={20} className="text-white/50" />
            <h2 className="text-white font-medium">Sobre</h2>
          </div>
          <div className="space-y-2 text-sm text-white/60">
            <div className="flex justify-between">
              <span>Versão</span>
              <span className="text-white/90">3.0.0</span>
            </div>
            <div className="flex justify-between">
              <span>Plataforma</span>
              <span className="text-white/90">PWA Mobile</span>
            </div>
            <div className="flex justify-between">
              <span>Backend</span>
              <span className="text-white/90">localhost:8742</span>
            </div>
          </div>
        </div>

        {/* Logout */}
        <button
          onClick={handleLogout}
          className="w-full glass-dark rounded-2xl p-4 flex items-center justify-center gap-3 text-red-400 font-medium transition-all active:scale-95 hover:bg-red-500/10"
        >
          <LogOut size={20} />
          <span>Sair da Conta</span>
        </button>

        {/* Footer */}
        <div className="text-center text-white/30 text-xs pb-4">
          Ahri V3 • AI Companion System
        </div>
      </div>
    </div>
  );
}
