/**
 * InstrucoesTab — Layer 1: Explicit User Preferences
 *
 * The user defines static parameters here. The AI NEVER writes to these fields.
 * This replaces the old "Profile" tab, which mixed manual and AI-generated data.
 */
import React, { useState, useEffect } from 'react';
import { Save, User, MessageSquare, Shield, RefreshCw } from 'lucide-react';
import { api } from '@/api/client';
import type { UserPreferences } from '@ahri/shared/types/memory';

const DEFAULT_PREFS: UserPreferences = {
  display_name: '',
  pronouns: '',
  occupation: '',
  location: '',
  custom_instructions: '',
  topics_to_avoid: '',
  persona_style: '',
};

export function InstrucoesTab() {
  const [prefs, setPrefs] = useState<UserPreferences>(DEFAULT_PREFS);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedFeedback, setSavedFeedback] = useState(false);

  useEffect(() => {
    api.getPreferences()
      .then((data) => setPrefs(data))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const handleChange = (field: keyof UserPreferences, value: string) => {
    setPrefs((prev) => ({ ...prev, [field]: value }));
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const updated = await api.updatePreferences(prefs);
      setPrefs(updated);
      setSavedFeedback(true);
      setTimeout(() => setSavedFeedback(false), 2500);
    } catch (err) {
      console.error('Failed to save preferences:', err);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <RefreshCw className="animate-spin w-6 h-6" style={{ color: 'var(--text-tertiary)' }} />
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-2xl">
      {/* Header */}
      <div>
        <h2 className="text-xl font-semibold mb-1" style={{ color: 'var(--text-primary)' }}>
          Instruções Personalizadas
        </h2>
        <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
          Parâmetros fixos que você define. A IA <strong>nunca</strong> altera estes campos — apenas você.
        </p>
      </div>

      {/* Identidade */}
      <Section icon={<User size={16} />} title="Identidade">
        <div className="grid grid-cols-2 gap-4">
          <Field
            label="Nome"
            placeholder="Como a Ahri deve te chamar"
            value={prefs.display_name}
            onChange={(v) => handleChange('display_name', v)}
          />
          <Field
            label="Pronomes"
            placeholder="ex: ele/dele, ela/dela"
            value={prefs.pronouns}
            onChange={(v) => handleChange('pronouns', v)}
          />
        </div>
      </Section>

      {/* Diretrizes de Resposta */}
      <Section icon={<MessageSquare size={16} />} title="Diretrizes de Resposta">
        <p className="text-xs mb-3" style={{ color: 'var(--text-tertiary)' }}>
          Escreva em linguagem natural como a IA deve se comportar, tom preferido, formato de respostas, etc.
        </p>
        <textarea
          className="settings-input resize-none"
          style={{ minHeight: '120px' }}
          placeholder="ex: Prefiro respostas diretas e sem enrolação. Gosto de exemplos práticos. Quando eu errar algo, me corrija sem rodeios."
          value={prefs.custom_instructions}
          onChange={(e) => handleChange('custom_instructions', e.target.value)}
        />
      </Section>

      {/* Limites e Estilo */}
      <Section icon={<Shield size={16} />} title="Limites">
        <label className="block text-xs font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>
          Tópicos a Evitar
        </label>
        <textarea
          className="settings-input resize-none"
          style={{ minHeight: '72px' }}
          placeholder="ex: política, religião, esportes"
          value={prefs.topics_to_avoid}
          onChange={(e) => handleChange('topics_to_avoid', e.target.value)}
        />
      </Section>

      {/* Save */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition-all disabled:opacity-60"
          style={{ background: 'var(--persona-primary)', color: '#fff' }}
        >
          {saving ? <RefreshCw size={14} className="animate-spin" /> : <Save size={14} />}
          {saving ? 'Salvando...' : 'Salvar Instruções'}
        </button>
        {savedFeedback && (
          <span className="text-sm" style={{ color: 'var(--persona-primary)' }}>
            ✓ Salvo com sucesso
          </span>
        )}
      </div>

      {/* Info note */}
      <div
        className="rounded-xl px-4 py-3 text-xs"
        style={{ background: 'var(--glass-bg)', border: '1px solid var(--glass-border)', color: 'var(--text-tertiary)' }}
      >
        <strong style={{ color: 'var(--text-secondary)' }}>Layer 1 — Preferências Explícitas.</strong>{' '}
        Estas configurações são injetadas em toda conversa com prioridade máxima. A memória dinâmica (Layer 2) fica na aba <em>Memória IA</em>.
      </div>
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────────────

function Section({ icon, title, children }: { icon: React.ReactNode; title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3
        className="flex items-center gap-2 text-sm font-semibold mb-4"
        style={{ color: 'var(--text-secondary)' }}
      >
        <span style={{ color: 'var(--persona-primary)' }}>{icon}</span>
        {title}
      </h3>
      {children}
    </div>
  );
}

function Field({
  label, placeholder, value, onChange, icon,
}: {
  label: string;
  placeholder: string;
  value: string;
  onChange: (v: string) => void;
  icon?: React.ReactNode;
}) {
  return (
    <div>
      <label className="block text-xs font-medium mb-1.5" style={{ color: 'var(--text-secondary)' }}>
        {icon ? <span className="flex items-center gap-1.5">{icon}{label}</span> : label}
      </label>
      <input
        type="text"
        className="settings-input"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
