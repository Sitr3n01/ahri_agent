/**
 * ChatHeader - Mobile chat header with persona info
 */

import { usePersonaStore } from '@/stores/persona-store';
import { useChatStore } from '@/stores/chat-store';
import { Menu } from 'lucide-react';

export function ChatHeader() {
  const activePersona = usePersonaStore((s) => s.activePersona);
  const model = useChatStore((s) => s.model);

  const modelLabels = {
    PRO: 'Gemini Pro',
    GOOGLE: 'Flash Lite',
    DEEPSEEK: 'DeepSeek R1',
    LOCAL: 'Local'
  };

  return (
    <div className="h-16 border-b border-white/10 bg-black/40 backdrop-blur-xl px-4 flex items-center justify-between">
      {/* Persona Info */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-full bg-gradient-to-br from-[var(--theme-primary)] to-[var(--theme-accent)] flex items-center justify-center">
          <span className="text-xl">✨</span>
        </div>
        <div>
          <h2 className="text-white font-medium">
            {activePersona?.name || 'Ahri'}
          </h2>
          <p className="text-white/50 text-xs">
            {modelLabels[model]}
          </p>
        </div>
      </div>

      {/* Menu Button */}
      <button className="w-10 h-10 rounded-xl bg-white/10 hover:bg-white/20 flex items-center justify-center transition-all active:scale-95">
        <Menu size={20} className="text-white/70" />
      </button>
    </div>
  );
}
