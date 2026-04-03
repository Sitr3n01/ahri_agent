import React, { useState, useEffect, useCallback } from 'react';
import { usePersonaStore } from '@/stores/persona-store';
import { useI18nStore } from '@/stores/i18n-store';
import {
  Brain, Database, Globe, BookOpen, Sparkles, ChevronDown, ChevronRight,
  Zap, Target, Clock, Briefcase, User, Archive, RefreshCw,
} from 'lucide-react';
import { api } from '@/api/client';
import type { SemanticMemoryItem, SemanticTiersResponse } from '@ahri/shared/types/memory';
import { SemanticTierSection } from './memory/SemanticTierSection';
import { PersonaMemorySection } from './memory/PersonaMemorySection';
import { RagMemoriesSection } from './memory/RagMemoriesSection';
import { SocialGraphSection } from './memory/SocialGraphSection';
import { EpisodicMemorySection } from './memory/EpisodicMemorySection';

export function MemoryTab() {
  const { locale } = useI18nStore();
  const personas = usePersonaStore((s) => s.personas);
  const activePersona = usePersonaStore((s) => s.activePersona);
  const [selectedPersona, setSelectedPersona] = useState(activePersona);

  // Shared semantic tiers data — fetched once, passed down to avoid N+1 calls
  const [tiersData, setTiersData] = useState<Record<string, SemanticMemoryItem[]>>({});
  const [tiersLoading, setTiersLoading] = useState(true);
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(['immediate_context', 'top_of_mind'])
  );

  const loadTiers = useCallback(async () => {
    setTiersLoading(true);
    try {
      const data: SemanticTiersResponse = await api.getSemanticTiers();
      setTiersData(data as unknown as Record<string, SemanticMemoryItem[]>);
    } catch (err) {
      console.error('Failed to load semantic tiers:', err);
    } finally {
      setTiersLoading(false);
    }
  }, []);

  useEffect(() => { loadTiers(); }, [loadTiers]);

  const toggleSection = (id: string) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  // ── Section definitions ────────────────────────────────────────
  const semanticSections = [
    {
      id: 'immediate_context',
      label: locale === 'pt' ? 'Contexto Imediato' : 'Immediate Context',
      description: locale === 'pt'
        ? 'Estado emocional e eventos de hoje — expira em 48h'
        : 'Emotional state and today\'s events — expires in 48h',
      icon: <Zap size={16} className="text-red-400" />,
      allowDelete: true,
    },
    {
      id: 'top_of_mind',
      label: locale === 'pt' ? 'Foco Atual' : 'Top of Mind',
      description: locale === 'pt'
        ? 'Projetos ativos e preocupações recorrentes — expira em 7 dias'
        : 'Active projects and recurring concerns — expires in 7 days',
      icon: <Target size={16} className="text-orange-400" />,
      allowDelete: true,
    },
    {
      id: 'recent_history',
      label: locale === 'pt' ? 'Histórico Recente' : 'Recent History',
      description: locale === 'pt'
        ? 'Eventos significativos dos últimos 7–14 dias'
        : 'Significant events from the last 7–14 days',
      icon: <Clock size={16} className="text-yellow-400" />,
      allowDelete: true,
    },
    {
      id: 'work_context',
      label: locale === 'pt' ? 'Contexto Profissional' : 'Work Context',
      description: locale === 'pt'
        ? 'Background profissional e projetos — atualizado por síntese'
        : 'Professional background and projects — refreshed by synthesis',
      icon: <Briefcase size={16} className="text-blue-400" />,
      allowDelete: false,
    },
    {
      id: 'personal_context',
      label: locale === 'pt' ? 'Contexto Pessoal' : 'Personal Context',
      description: locale === 'pt'
        ? 'Relacionamentos, hobbies e interesses — atualizado por síntese'
        : 'Relationships, hobbies, and interests — refreshed by synthesis',
      icon: <User size={16} className="text-pink-400" />,
      allowDelete: false,
    },
    {
      id: 'long_term_background',
      label: locale === 'pt' ? 'Histórico de Longo Prazo' : 'Long-term Background',
      description: locale === 'pt'
        ? 'Fatos biográficos estáveis e valores centrais — sem decay'
        : 'Stable biographical facts and core values — no decay',
      icon: <Archive size={16} className="text-purple-400" />,
      allowDelete: false,
    },
  ];

  const personaSections = [
    {
      id: 'persona-memory',
      label: locale === 'pt' ? 'Memória da Persona' : 'Persona Memory',
      description: locale === 'pt'
        ? 'Quests, logs de sessão e buffer específicos de cada persona'
        : 'Per-persona quests, session logs, and context buffer',
      icon: <Sparkles size={16} className="text-pink-400" />,
      content: <PersonaMemorySection persona={selectedPersona} />,
    },
    {
      id: 'rag-memories',
      label: locale === 'pt' ? 'Memórias RAG' : 'RAG Memories',
      description: locale === 'pt'
        ? 'Base de conhecimento vetorial por persona (ChromaDB)'
        : 'Per-persona vector knowledge base (ChromaDB)',
      icon: <Database size={16} className="text-emerald-400" />,
      content: <RagMemoriesSection persona={selectedPersona} />,
    },
    {
      id: 'social-graph',
      label: locale === 'pt' ? 'Perfil Social' : 'Social Profile',
      description: locale === 'pt'
        ? 'Análise de perfil importada de redes sociais'
        : 'Profile analysis imported from social networks',
      icon: <Globe size={16} className="text-blue-400" />,
      content: <SocialGraphSection />,
    },
    {
      id: 'episodic',
      label: locale === 'pt' ? 'Memória Episódica' : 'Episodic Memory',
      description: locale === 'pt'
        ? 'Resumos de sessões passadas com contexto emocional'
        : 'Past session summaries with emotional context',
      icon: <BookOpen size={16} className="text-amber-400" />,
      content: <EpisodicMemorySection persona={selectedPersona} />,
    },
  ];

  return (
    <div className="flex flex-col gap-6 pb-10">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-bold text-[var(--text-primary)]">
            {locale === 'pt' ? 'Memória IA — Layer 2' : 'AI Memory — Layer 2'}
          </h2>
          <p className="text-[10px] mt-1 text-[var(--text-tertiary)] max-w-md">
            {locale === 'pt'
              ? 'Contexto dinâmico gerado automaticamente pela IA. Para instruções fixas, use a aba Instruções.'
              : 'Dynamic context automatically generated by AI. For fixed instructions, use the Instructions tab.'}
          </p>
        </div>
        <div className="flex items-center gap-3 self-start sm:self-center">
          {/* Refresh tiers */}
          <button
            onClick={loadTiers}
            disabled={tiersLoading}
            className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-lg transition-all opacity-70 hover:opacity-100"
            style={{ background: 'var(--glass-bg)', border: '1px solid var(--glass-border)', color: 'var(--text-secondary)' }}
          >
            <RefreshCw size={12} className={tiersLoading ? 'animate-spin' : ''} />
            {locale === 'pt' ? 'Atualizar' : 'Refresh'}
          </button>
          {/* Persona selector */}
          <div className="flex items-center gap-2">
            <label className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-tertiary)]">
              Persona
            </label>
            <select
              value={selectedPersona}
              onChange={(e) => setSelectedPersona(e.target.value)}
              className="settings-input text-xs py-1.5 px-3 min-w-[160px] bg-[var(--surface-solid)] border-[var(--glass-border)]"
            >
              {personas.map((p: any) => (
                <option key={p.name} value={p.name}>
                  {p.display_name || p.name}
                  {p.name === activePersona ? ' (ativa)' : ''}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* ── Semantic Tier Sections (Layer 2) ── */}
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--persona-primary)' }}>
          {locale === 'pt' ? 'Tiers Semânticos' : 'Semantic Tiers'}
        </p>
        <div className="flex flex-col gap-3">
          {semanticSections.map((section) => {
            const isExpanded = expandedSections.has(section.id);
            const count = (tiersData[section.id] || []).length;
            return (
              <div
                key={section.id}
                className="rounded-2xl border overflow-hidden transition-all"
                style={{ borderColor: 'var(--glass-border)', background: 'var(--surface-solid)' }}
              >
                <button
                  onClick={() => toggleSection(section.id)}
                  className="w-full flex items-center gap-3 p-4 text-left hover:bg-white/[0.02] transition-colors"
                >
                  {section.icon}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="text-sm font-semibold text-[var(--text-primary)]">{section.label}</h3>
                      {count > 0 && (
                        <span
                          className="text-[10px] px-1.5 py-0.5 rounded-full font-medium"
                          style={{ background: 'var(--persona-primary)22', color: 'var(--persona-primary)' }}
                        >
                          {count}
                        </span>
                      )}
                    </div>
                    <p className="text-[10px] text-[var(--text-tertiary)] mt-0.5">{section.description}</p>
                  </div>
                  {isExpanded
                    ? <ChevronDown size={16} className="text-[var(--text-tertiary)] flex-shrink-0" />
                    : <ChevronRight size={16} className="text-[var(--text-tertiary)] flex-shrink-0" />}
                </button>
                {isExpanded && (
                  <div className="px-4 pb-4 pt-0 border-t animate-fade-in" style={{ borderColor: 'var(--glass-border)', animationDuration: '0.2s' }}>
                    <SemanticTierSection
                      tier={section.id as any}
                      label={section.label}
                      allowDelete={section.allowDelete}
                      tiersData={tiersData}
                      onRefresh={loadTiers}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Persona & Legacy Sections ── */}
      <div>
        <p className="text-[10px] font-semibold uppercase tracking-wider mb-3" style={{ color: 'var(--text-tertiary)' }}>
          {locale === 'pt' ? 'Memória por Persona' : 'Per-Persona Memory'}
        </p>
        <div className="flex flex-col gap-3">
          {personaSections.map((section) => {
            const isExpanded = expandedSections.has(section.id);
            return (
              <div
                key={section.id}
                className="rounded-2xl border overflow-hidden transition-all"
                style={{ borderColor: 'var(--glass-border)', background: 'var(--surface-solid)' }}
              >
                <button
                  onClick={() => toggleSection(section.id)}
                  className="w-full flex items-center gap-3 p-4 text-left hover:bg-white/[0.02] transition-colors"
                >
                  {section.icon}
                  <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-semibold text-[var(--text-primary)]">{section.label}</h3>
                    <p className="text-[10px] text-[var(--text-tertiary)] mt-0.5">{section.description}</p>
                  </div>
                  {isExpanded
                    ? <ChevronDown size={16} className="text-[var(--text-tertiary)] flex-shrink-0" />
                    : <ChevronRight size={16} className="text-[var(--text-tertiary)] flex-shrink-0" />}
                </button>
                {isExpanded && (
                  <div className="px-5 pb-5 pt-0 border-t animate-fade-in" style={{ borderColor: 'var(--glass-border)', animationDuration: '0.2s' }}>
                    {section.content}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
